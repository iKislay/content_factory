# tools/executor.py
"""
ToolCall, ToolResult dataclasses + ToolExecutor.

ToolExecutor is a stateless dispatcher — it looks up the tool in the registry,
executes it, captures exceptions into ToolResult.error, and records wall-clock
execution time. An optional trace_fn callback fires after every execution so
agents can post TOOL_CALLED / TOOL_RESULT messages to the blackboard.

Includes retry with exponential backoff for transient failures.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from tools.registry import ToolRegistry

import config
from circuit_breaker import get_circuit_breaker, CircuitState


# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class ToolCall:
    """
    A request from the LLM (or from an agent) to invoke a named tool.

    Attributes:
        tool_name:  Matches a key in the ToolRegistry.
        arguments:  Keyword arguments to pass to the tool function.
        call_id:    Opaque identifier (from Groq or synthetically generated).
    """

    tool_name: str
    arguments: dict = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class ToolResult:
    """
    The outcome of executing a ToolCall.

    Attributes:
        tool_name:    Echo of ToolCall.tool_name.
        call_id:      Echo of ToolCall.call_id.
        output:       Whatever the tool function returned (None on error).
        error:        Exception message if the tool raised; None on success.
        duration_ms:  Wall-clock execution time in milliseconds.
    """

    tool_name: str
    call_id: str
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

    def is_ok(self) -> bool:
        """True when the tool completed without error."""
        return self.error is None

    def to_summary(self) -> str:
        """Compact, one-line string safe for logging or prompt injection."""
        if self.error:
            return f"ERROR: {self.error}"
        if isinstance(self.output, list):
            return f"{len(self.output)} item(s) returned"
        if isinstance(self.output, dict):
            return json.dumps(self.output)[:300]
        if isinstance(self.output, str):
            return self.output[:300]
        return str(self.output)[:300]

    def to_llm_content(self) -> str:
        """Serialise output for injection into a tool-role message."""
        if self.error:
            return f"Error executing {self.tool_name}: {self.error}"
        try:
            return json.dumps(self.output, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(self.output)


# ─── Executor ─────────────────────────────────────────────────────────────────


class ToolExecutor:
    """
    Dispatches ToolCalls to registered tool functions.

    Thread-safe: each call is fully self-contained (no shared mutable state).
    The optional trace_fn fires synchronously after each execution — keep it
    fast (e.g. a SQLite write) to avoid stalling tool threads.

    Args:
        registry:  The ToolRegistry to look tools up in.
        trace_fn:  Optional callback(ToolCall, ToolResult) for observability.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        trace_fn: Optional[Callable[[ToolCall, ToolResult], None]] = None,
    ) -> None:
        self._registry = registry
        self._trace_fn = trace_fn

    def execute(self, call: ToolCall) -> ToolResult:
        """
        Execute *call* and return a ToolResult.

        Implements retry with exponential backoff for transient failures.
        Circuit breaker pattern prevents repeated calls to failing tools.
        Never raises — exceptions from the tool function are captured into
        ToolResult.error so the LLM can reason about the failure.
        """
        circuit_breaker = get_circuit_breaker()
        tool_def = self._registry.get(call.tool_name)

        if tool_def is None:
            result = ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                error=f"Unknown tool '{call.tool_name}'. "
                      f"Available: {self._registry.names()}",
            )
            if self._trace_fn:
                self._trace_fn(call, result)
            return result

        if tool_def.fallback_fn is not None and circuit_breaker.should_use_fallback(call.tool_name):
            if self._trace_fn:
                circuit_call = ToolCall(
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                    call_id=f"{call.call_id}-circuit"
                )
                circuit_log = ToolResult(
                    tool_name=call.tool_name,
                    call_id=circuit_call.call_id,
                    error=f"Circuit breaker active - using fallback for {call.tool_name}",
                    duration_ms=0,
                )
                self._trace_fn(circuit_call, circuit_log)
            return self._execute_fallback(tool_def, call, None)

        max_retries = config.TOOL_MAX_RETRIES
        base_delay = config.TOOL_RETRY_BASE_DELAY
        max_delay = config.TOOL_RETRY_MAX_DELAY
        backoff_factor = config.TOOL_RETRY_BACKOFF

        last_error = None
        total_duration_ms = 0.0

        for attempt in range(max_retries + 1):
            t0 = time.monotonic()
            try:
                output = tool_def.fn(**call.arguments)
                result = ToolResult(
                    tool_name=call.tool_name,
                    call_id=call.call_id,
                    output=output,
                    duration_ms=round((time.monotonic() - t0) * 1000, 1),
                )
                if attempt > 0:
                    result.error = f"Recovered after {attempt} retry(s). Original error: {last_error}"
                circuit_breaker.record_success(call.tool_name)
                if self._trace_fn:
                    self._trace_fn(call, result)
                return result
            except Exception as exc:
                last_error = str(exc)
                attempt_duration = round((time.monotonic() - t0) * 1000, 1)
                total_duration_ms += attempt_duration

                if attempt < max_retries:
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    if self._trace_fn:
                        retry_call = ToolCall(
                            tool_name=call.tool_name,
                            arguments=call.arguments,
                            call_id=f"{call.call_id}-retry-{attempt}"
                        )
                        retry_result = ToolResult(
                            tool_name=call.tool_name,
                            call_id=retry_call.call_id,
                            error=f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {last_error}",
                            duration_ms=attempt_duration,
                        )
                        self._trace_fn(retry_call, retry_result)
                    time.sleep(delay)
                    continue

                result = ToolResult(
                    tool_name=call.tool_name,
                    call_id=call.call_id,
                    error=f"Failed after {max_retries} retries. Last error: {last_error}",
                    duration_ms=total_duration_ms,
                )

                circuit_breaker.record_failure(call.tool_name)

                # Try fallback if available
                if tool_def.fallback_fn is not None:
                    fallback_result = self._execute_fallback(tool_def, call, result)
                    if fallback_result is not None:
                        return fallback_result

        if self._trace_fn:
            self._trace_fn(call, result)

        return result

    def _execute_fallback(
        self,
        tool_def: ToolDef,
        call: ToolCall,
        failed_result: ToolResult
    ) -> Optional[ToolResult]:
        """Execute fallback function when primary tool fails."""
        fallback_name = getattr(tool_def.fallback_fn, '__name__', 'fallback')
        
        if self._trace_fn:
            fallback_call = ToolCall(
                tool_name=f"fallback:{tool_def.name}",
                arguments=call.arguments,
                call_id=f"{call.call_id}-fallback"
            )
            fallback_log = ToolResult(
                tool_name=tool_def.name,
                call_id=fallback_call.call_id,
                error=f"Fallback activated: {fallback_name}",
                duration_ms=0,
            )
            self._trace_fn(fallback_call, fallback_log)

        try:
            t0 = time.monotonic()
            output = tool_def.fallback_fn(**call.arguments)
            result = ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                output=output,
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
            )
            result.error = f"DEGRADED: Used fallback ({fallback_name}). Original error: {failed_result.error}"
            if self._trace_fn:
                self._trace_fn(call, result)
            return result
        except Exception as fallback_exc:
            result = ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                error=f"Fallback '{fallback_name}' also failed. Primary error: {failed_result.error}. Fallback error: {str(fallback_exc)}",
                duration_ms=0,
            )
            if self._trace_fn:
                self._trace_fn(call, result)
            return result

    def execute_many(self, calls: List[ToolCall]) -> List[ToolResult]:
        """Execute a list of ToolCalls sequentially and return all results."""
        return [self.execute(call) for call in calls]
