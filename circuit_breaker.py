import threading
import time
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import config
import logger
_log = logger.get_pipeline_logger("circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing - use fallback
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker for a single tool."""
    name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    failure_timestamps: List[float] = field(default_factory=list)
    last_failure_time: Optional[float] = None
    open_time: Optional[float] = None
    half_open_attempts: int = 0


class CircuitBreakerManager:
    """
    Manages circuit breakers for all tools.
    
    Tracks failures per tool and manages circuit state transitions:
    - CLOSED -> OPEN: after threshold failures in timeout window
    - OPEN -> HALF_OPEN: after cooldown period expires
    - HALF_OPEN -> CLOSED: on successful call
    - HALF_OPEN -> OPEN: on failed call in half-open state
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_breaker(self, tool_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for a tool."""
        with self._lock:
            if tool_name not in self._breakers:
                self._breakers[tool_name] = CircuitBreaker(name=tool_name)
            return self._breakers[tool_name]

    def record_success(self, tool_name: str) -> None:
        """Record a successful call - may close an open circuit."""
        breaker = self.get_breaker(tool_name)
        with self._lock:
            if breaker.state == CircuitState.HALF_OPEN:
                breaker.half_open_attempts += 1
                if breaker.half_open_attempts >= config.CIRCUIT_HALF_OPEN_RETRIES:
                    self._reset_circuit(breaker)
            elif breaker.state == CircuitState.CLOSED:
                breaker.failure_count = max(0, breaker.failure_count - 1)
                if breaker.failure_timestamps:
                    self._clean_old_failures(breaker)

    def record_failure(self, tool_name: str) -> None:
        """Record a failed call - may open the circuit."""
        breaker = self.get_breaker(tool_name)
        current_time = time.time()

        with self._lock:
            if breaker.state == CircuitState.HALF_OPEN:
                breaker.half_open_attempts += 1
                if breaker.half_open_attempts >= config.CIRCUIT_HALF_OPEN_RETRIES:
                    self._open_circuit(breaker)
                return

            now = time.time()
            breaker.failure_timestamps.append(now)
            breaker.last_failure_time = now
            self._clean_old_failures(breaker)

            breaker.failure_count = len(breaker.failure_timestamps)

            if breaker.failure_count >= config.CIRCUIT_FAILURE_THRESHOLD:
                self._open_circuit(breaker)

    def _open_circuit(self, breaker: CircuitBreaker) -> None:
        """Open the circuit (start using fallback)."""
        breaker.state = CircuitState.OPEN
        breaker.open_time = time.time()
        breaker.failure_count = 0
        breaker.failure_timestamps = []
        print(f"[CIRCUIT] 🔴 OPEN: {breaker.name} - too many failures, using fallback")
        _log.circuit_breaker(tool=breaker.name, state="open", reason="threshold_exceeded")

    def _reset_circuit(self, breaker: CircuitBreaker) -> None:
        """Reset circuit to closed state (normal operation)."""
        breaker.state = CircuitState.CLOSED
        breaker.open_time = None
        breaker.failure_count = 0
        breaker.failure_timestamps = []
        breaker.half_open_attempts = 0
        print(f"[CIRCUIT] 🟢 CLOSED: {breaker.name} - recovered, normal operation")
        _log.circuit_breaker(tool=breaker.name, state="closed", reason="recovered")

    def _clean_old_failures(self, breaker: CircuitBreaker) -> None:
        """Remove failures outside the timeout window."""
        cutoff = time.time() - config.CIRCUIT_TIMEOUT_WINDOW_SEC
        breaker.failure_timestamps = [ts for ts in breaker.failure_timestamps if ts > cutoff]
        breaker.failure_count = len(breaker.failure_timestamps)

    def should_use_fallback(self, tool_name: str) -> bool:
        """
        Determine if fallback should be used.
        Returns True if circuit is OPEN or HALF_OPEN (failed attempt).
        """
        breaker = self.get_breaker(tool_name)
        with self._lock:
            if breaker.state == CircuitState.CLOSED:
                return False
            
            if breaker.state == CircuitState.OPEN:
                if breaker.open_time and (time.time() - breaker.open_time) >= config.CIRCUIT_COOLDOWN_SEC:
                    breaker.state = CircuitState.HALF_OPEN
                    breaker.half_open_attempts = 0
                    print(f"[CIRCUIT] 🟡 HALF_OPEN: {breaker.name} - testing recovery")
                    _log.circuit_breaker(tool=breaker.name, state="half_open", reason="cooldown_expired")
                    return True
                return True
            
            if breaker.state == CircuitState.HALF_OPEN:
                return True
            
            return False

    def get_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers (for debugging)."""
        with self._lock:
            return {
                name: {
                    "state": breaker.state.value,
                    "failure_count": breaker.failure_count,
                    "last_failure": breaker.last_failure_time,
                    "open_time": breaker.open_time,
                }
                for name, breaker in self._breakers.items()
            }


_circuit_breaker_manager = CircuitBreakerManager()


def get_circuit_breaker() -> CircuitBreakerManager:
    """Get the global circuit breaker manager."""
    return _circuit_breaker_manager