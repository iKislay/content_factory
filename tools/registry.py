# tools/registry.py
"""
ToolRegistry — central catalogue of all agentic tools.

Tools are registered via the @registry.tool() decorator. The registry exposes
two schema formats:
  - to_groq_schema()   : list[dict] in OpenAI/Groq function-calling format
  - to_ollama_text()   : plain-text description for the Ollama fallback prompt

Usage:
    registry = ToolRegistry()

    @registry.tool(
        name="web_search",
        description="Search the web via DuckDuckGo.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    )
    def web_search(query: str) -> list:
        ...
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolDef:
    """Metadata + implementation for a single tool."""

    name: str
    description: str
    parameters: Dict[str, Any]   # JSON Schema object
    fn: Callable
    fallback_fn: Optional[Callable] = None  # Fallback function if primary fails


class ToolRegistry:
    """
    Central catalogue that maps tool names to ToolDef instances.

    Thread-safe for reads; registrations should happen at import time only.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDef] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        fallback: Optional[Callable] = None,
    ) -> Callable:
        """
        Decorator factory.  Registers the decorated function as a tool.

        Args:
            name: Tool name
            description: Human-readable description
            parameters: JSON Schema for parameters
            fallback: Optional fallback function to use when primary fails

        Example::

            @registry.tool("web_search", "Search the web", {...})
            def web_search(query: str) -> list: ...

            # With fallback
            @registry.tool("generate_image", "Generate image", {...}, fallback=fallback_image)
            def generate_image(prompt: str) -> str: ...
        """
        def decorator(fn: Callable) -> Callable:
            self._tools[name] = ToolDef(
                name=name,
                description=description,
                parameters=parameters,
                fn=fn,
                fallback_fn=fallback,
            )
            return fn

        return decorator

    def get(self, name: str) -> Optional[ToolDef]:
        """Return the ToolDef for *name*, or None if not registered."""
        return self._tools.get(name)

    def names(self) -> List[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    # ── Schema serialisation ──────────────────────────────────────────────────

    def to_groq_schema(self, names: Optional[List[str]] = None) -> List[Dict]:
        """
        Convert (a subset of) registered tools to Groq/OpenAI function-calling
        format: list of {"type": "function", "function": {...}} dicts.

        Args:
            names: If given, only include these tool names. Default = all.
        """
        selected = (
            [self._tools[n] for n in names if n in self._tools]
            if names
            else list(self._tools.values())
        )
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in selected
        ]

    def to_ollama_text(self, names: Optional[List[str]] = None) -> str:
        """
        Plain-text tool catalogue for the Ollama fallback prompt.
        """
        selected = (
            [self._tools[n] for n in names if n in self._tools]
            if names
            else list(self._tools.values())
        )
        lines = ["Available tools (call them by name):"]
        for t in selected:
            props = t.parameters.get("properties", {})
            param_str = ", ".join(
                f"{k}: {v.get('type', 'any')}" for k, v in props.items()
            )
            lines.append(f"  • {t.name}({param_str}) — {t.description}")
        return "\n".join(lines)


# ── Global singleton ───────────────────────────────────────────────────────────
# All tool definitions import this and register via @registry.tool(...)
registry = ToolRegistry()
