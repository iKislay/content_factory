# tools/__init__.py
"""
Agentic tool system for content_factory.

Importing this package triggers tool registration (via tools.definitions).
Agents use generate_with_tools() from providers.llm to let the LLM drive
tool selection and execution autonomously.

Exports:
    registry    — global ToolRegistry singleton
    ToolCall    — dataclass representing an LLM tool invocation request
    ToolResult  — dataclass representing the outcome of a tool execution
    ToolExecutor — dispatches ToolCalls, captures errors, fires trace callbacks
"""

from tools.registry import registry, ToolDef, ToolRegistry
from tools.executor import ToolCall, ToolResult, ToolExecutor

# Trigger registration of all 5 concrete tools
import tools.definitions  # noqa: F401

__all__ = [
    "registry",
    "ToolDef",
    "ToolRegistry",
    "ToolCall",
    "ToolResult",
    "ToolExecutor",
]
