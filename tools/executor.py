# tools/executor.py
"""
ToolCall, ToolResult dataclasses + ToolExecutor.

ToolExecutor is a stateless dispatcher — it looks up the tool in the registry,
executes it, captures exceptions into ToolResult.error, and records wall-clock
execution time. An optional trace_fn callback fires after every execution so
agents can post TOOL_CALLED / TOOL_RESULT messages to the blackboard.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from tools.registry import ToolRegistry


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

        Never raises — exceptions from the tool function are captured into
        ToolResult.error so the LLM can reason about the failure.
        """
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

        t0 = time.monotonic()
        try:
            output = tool_def.fn(**call.arguments)
            result = ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                output=output,
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
            )
        except Exception as exc:
            result = ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                error=str(exc),
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
            )

        if self._trace_fn:
            self._trace_fn(call, result)

        return result

    def execute_many(self, calls: List[ToolCall]) -> List[ToolResult]:
        """Execute a list of ToolCalls sequentially and return all results."""
        return [self.execute(call) for call in calls]
