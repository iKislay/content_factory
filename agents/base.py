# agents/base.py
"""
Base agent class and AgentResult dataclass.

All specialist agents inherit from BaseAgent. Communication between agents
happens through the shared SQLite blackboard (state.py agent_messages table),
not through direct function calls. This ensures every decision is durable,
crash-safe, and inspectable.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from state import PipelineState


# ─── Typed Handoff ────────────────────────────────────────────────────────────


@dataclass
class AgentResult:
    """
    Structured result returned by every agent run().

    Attributes:
        success:    Whether the agent completed its task without fatal error.
        output:     Structured output payload for the next agent.
        next_agent: Name of the agent that should run next (set by agent,
                    honoured by Orchestrator).
        reasoning:  Human-readable explanation of what this agent decided and why.
        errors:     Non-fatal issues encountered (fatal issues raise exceptions).
    """

    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    next_agent: Optional[str] = None
    reasoning: str = ""
    errors: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return (
            f"AgentResult({status} next={self.next_agent!r} "
            f"errors={len(self.errors)})"
        )


# ─── Base Agent ───────────────────────────────────────────────────────────────


class BaseAgent(ABC):
    """
    Abstract base class for all pipeline agents.

    Subclasses must implement run(). They communicate with each other via
    the shared blackboard (post_message / read_messages) rather than direct
    imports or return values passed between callers.
    """

    #: Override in each subclass with a short, unique identifier.
    name: str = "base"

    def __init__(self, state: PipelineState) -> None:
        self.state = state

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        """
        Execute this agent's task for the given run.

        Args:
            run_id:  The pipeline run identifier.
            context: Any additional context passed by the Orchestrator.

        Returns:
            AgentResult with success flag, output payload, and next agent hint.
        """
        ...

    # ── Blackboard helpers ────────────────────────────────────────────────────

    def post_message(
        self,
        run_id: str,
        msg_type: str,
        payload: Dict[str, Any],
        recipient: Optional[str] = None,
    ) -> str:
        """Post a message to the shared agent blackboard."""
        msg_id = self.state.post_message(
            run_id=run_id,
            sender=self.name,
            msg_type=msg_type,
            payload=payload,
            recipient=recipient,
        )
        self.log(f"→ blackboard [{msg_type}] id={msg_id[:8]}")
        return msg_id

    def read_messages(
        self, run_id: str, msg_type: Optional[str] = None
    ) -> List[dict]:
        """Read all messages from the blackboard for this run."""
        return self.state.get_messages(run_id, msg_type)

    def get_latest(self, run_id: str, msg_type: str) -> Optional[dict]:
        """Return the most recent blackboard message of a given type."""
        return self.state.get_latest_message(run_id, msg_type)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, msg: str) -> None:
        """Structured agent log line with timestamp."""
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}][{self.name.upper()}] {msg}")
