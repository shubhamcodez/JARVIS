"""Build the retrieval query from current turn and context."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# RouterState is TypedDict with message, goal, supervisor_decision, etc.
# We accept a minimal dict to avoid coupling to agents.state in case of circular imports.


def build_retrieval_query(
    current_message: str,
    recent_turns: Optional[List[Dict[str, str]]] = None,
    task_state: Optional[Dict[str, Any]] = None,
    active_file: Optional[str] = None,
    topic_or_entities: Optional[List[str]] = None,
) -> str:
    """
    Build a single string used as the retrieval query (will be embedded).
    Includes: current user message, recent assistant/user turns, task state, active file, entity names.
    """
    parts: List[str] = []

    current_message = (current_message or "").strip()
    if current_message:
        parts.append("Current request: " + current_message)

    if recent_turns:
        # Last N turns for context (e.g. last 2–4 messages)
        recent = recent_turns[-6:]  # up to 3 user + 3 assistant
        for t in recent:
            role = (t.get("role") or "user").strip().lower()
            content = (t.get("content") or "").strip()
            if content:
                parts.append(f"Recent ({role}): {content[:500]}")

    if task_state:
        goal = (task_state.get("goal") or "").strip()
        if goal:
            parts.append("Current task: " + goal)
        route = (task_state.get("route") or "").strip()
        if route:
            parts.append("Route: " + route)

    if active_file:
        parts.append("Active file or topic: " + active_file)

    if topic_or_entities:
        parts.append("Relevant topics or entities: " + ", ".join(topic_or_entities))

    return "\n".join(parts).strip() or "general context"
