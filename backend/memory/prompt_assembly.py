"""Assemble model context: current conversation + working state + retrieved memory."""
from __future__ import annotations

from typing import Optional

from .schemas import WorkingState


def inject_memory_into_user_message(
    user_message: str,
    memory_context: Optional[str] = None,
    working_state: Optional[WorkingState] = None,
) -> str:
    """
    Build the final user message by prepending memory context and optional working state.
    Used before sending to chat so the model sees: [context] + [current message].
    """
    parts = []
    if working_state and (
        working_state.current_task
        or working_state.active_files
        or working_state.recent_decisions
        or working_state.unresolved_questions
    ):
        ws_lines = []
        if working_state.current_task:
            ws_lines.append("Current task: " + working_state.current_task)
        if working_state.active_files:
            ws_lines.append("Active files: " + ", ".join(working_state.active_files))
        if working_state.recent_decisions:
            ws_lines.append("Recent decisions: " + "; ".join(working_state.recent_decisions[-3:]))
        if working_state.unresolved_questions:
            ws_lines.append("Unresolved: " + "; ".join(working_state.unresolved_questions[-3:]))
        if ws_lines:
            parts.append("Working context:\n" + "\n".join(ws_lines))
    if memory_context and memory_context.strip():
        parts.append(memory_context.strip())
    if user_message and user_message.strip():
        parts.append("Current message: " + user_message.strip())
    return "\n\n".join(parts) if parts else (user_message or "Hello.").strip() or "Hello."
