import threading
import asyncio
from typing import Dict, Any, Optional
from collections import defaultdict

_broadcast_lock = threading.Lock()
_pending_messages: Dict[str, list] = defaultdict(list)
_ws_manager = None

def init_broadcast(ws_manager):
    """Initialize the broadcast module with the WebSocket manager."""
    global _ws_manager
    _ws_manager = ws_manager

def broadcast_message(run_id: str, message_type: str, data: Dict[str, Any]):
    """Thread-safe function to broadcast a message to WebSocket clients."""
    with _broadcast_lock:
        _pending_messages[run_id].append({
            "type": message_type,
            "run_id": run_id,
            **data
        })

def get_messages(run_id: str) -> list:
    """Get and clear pending messages for a run."""
    with _broadcast_lock:
        messages = _pending_messages.get(run_id, [])
        _pending_messages[run_id] = []
        return messages

def clear_messages(run_id: str):
    """Clear pending messages for a run."""
    with _broadcast_lock:
        _pending_messages[run_id] = []

def emit_step_complete(run_id: str, agent: str, status: str, message: str = ""):
    broadcast_message(run_id, "step_complete", {
        "agent": agent,
        "status": status,
        "message": message or f"{agent.capitalize()} completed: {status}",
    })

def emit_progress_update(run_id: str, progress: int, current_agent: str, details: str = ""):
    broadcast_message(run_id, "progress_update", {
        "progress": progress,
        "current_agent": current_agent,
        "details": details,
    })

def emit_status_change(run_id: str, status: str, topic: str = ""):
    broadcast_message(run_id, "status_change", {
        "status": status,
        "topic": topic,
    })

def emit_agent_activity(run_id: str, agent: str, activity: str, details: Dict[str, Any] = None):
    broadcast_message(run_id, "agent_activity", {
        "agent": agent,
        "activity": activity,
        "details": details or {},
    })