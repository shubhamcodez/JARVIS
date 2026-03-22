"""State schemas for LangGraph flows (router graph)."""
from __future__ import annotations

from typing import Optional, TypedDict


class RouterState(TypedDict, total=False):
    """State for the main send_message router graph."""

    message: str
    attachment_paths: list[str]
    chat_id: Optional[str]
    api_key: str
    provider: str  # "openai" or "xai"
    route: str  # "chat" | "run_desktop" | "run_coding" | "run_shell" | "run_finance" (set by the node that ran)
    classification: dict
    supervisor_decision: dict
    goal: str
    reply: str
    on_step: Optional[object]  # optional callback for agent step streaming
    tool_used: Optional[dict]  # when chat used a tool: {"name", "input", "result"}
