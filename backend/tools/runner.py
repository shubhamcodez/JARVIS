"""
Tool-call layer: every turn gets full conversation history; then we run applicable tools
(weather, etc.) and return their results for the prompt. So: conversation (always) → tool calls → reply.
"""
from __future__ import annotations

from typing import Optional

from .python_sandbox import try_python_sandbox_tool
from .weather import try_weather_tool


def run_tools_for_turn(
    message: str,
    recent_turns: Optional[list[dict]] = None,
) -> tuple[str, Optional[dict]]:
    """
    Run all applicable tools for this turn (e.g. weather when the user asks about weather/temperature).
    Uses recent_turns so follow-ups (e.g. "exact temperature?") keep the same context (e.g. San Francisco).

    Returns:
        (system_content_from_tools, tool_used)
        - system_content_from_tools: block to add to system prompt (empty string if no tools ran)
        - tool_used: {"name", "input", "result"} for UI/persistence, or None
    """
    recent_turns = recent_turns or []
    system_blocks: list[str] = []
    tool_used = None

    # Python sandbox: user asked to run fenced ```python``` (pattern models can use)
    py_tool = try_python_sandbox_tool(message or "")
    if py_tool:
        py_block, tool_used = py_tool
        system_blocks.append(py_block)
        system_content = "\n\n".join(system_blocks) if system_blocks else ""
        return system_content, tool_used

    # Weather tool: when message is about weather/temperature/forecast
    weather_result = try_weather_tool(message or "", recent_turns=recent_turns)
    if weather_result:
        location, result = weather_result
        tool_used = {"name": "weather", "input": location, "result": result}
        system_blocks.append(
            f"REAL-TIME WEATHER DATA (you must use this): {result}\n"
            "Answer the user using ONLY this data. Do NOT say you lack access to real-time weather."
        )

    # Add more tools here (e.g. search, calculator) as needed

    system_content = "\n\n".join(system_blocks) if system_blocks else ""
    return system_content, tool_used
