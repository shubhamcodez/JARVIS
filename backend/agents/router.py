"""Router graph: supervisor decides route → chat | browser agent | desktop agent."""
from __future__ import annotations

import asyncio
from typing import Literal

from langgraph.graph import END, StateGraph

from .state import RouterState


async def _supervisor_node(state: RouterState) -> RouterState:
    from .supervisor import supervisor_decision

    message = (state.get("message") or "").strip()
    api_key = state["api_key"]
    decision = await asyncio.to_thread(supervisor_decision, api_key, message)
    goal = (decision.get("goal") or message).strip()
    return {"supervisor_decision": decision, "goal": goal}


async def _chat_node(state: RouterState) -> RouterState:
    from openai_client import chat as openai_chat

    api_key = state["api_key"]
    message = (state.get("message") or "").strip()
    paths = state.get("attachment_paths") or []
    if not message and paths:
        message = "Please summarize or answer based on the attached documents."
    reply = await asyncio.to_thread(
        openai_chat, api_key, message or "Hello.", paths if paths else None
    )
    return {"reply": reply}


def _emit_supervisor_step(state: RouterState) -> None:
    """Emit supervisor's next_steps as step 0 so the UI shows the plan."""
    on_step = state.get("on_step")
    if not on_step:
        return
    decision = state.get("supervisor_decision") or {}
    reasoning = decision.get("reasoning") or ""
    next_steps = decision.get("next_steps") or "Running agent."
    on_step(0, reasoning, "supervisor", next_steps, None, False)


async def _run_browser_node(state: RouterState) -> RouterState:
    from .browser_agent import run_browser_agent

    _emit_supervisor_step(state)
    goal = state.get("goal") or ""
    on_step = state.get("on_step")
    reply = await run_browser_agent(goal, 10, on_step, headless=False)
    return {"reply": reply}


async def _run_desktop_node(state: RouterState) -> RouterState:
    from .desktop_agent import run_desktop_agent

    _emit_supervisor_step(state)
    goal = state.get("goal") or ""
    on_step = state.get("on_step")
    reply = await asyncio.to_thread(run_desktop_agent, goal, 10, on_step)
    return {"reply": reply}


def _route_after_start(state: RouterState) -> Literal["chat", "supervisor"]:
    message = (state.get("message") or "").strip()
    paths = state.get("attachment_paths") or []
    if not message and paths:
        return "chat"
    return "supervisor"


def _route_after_supervisor(state: RouterState) -> Literal["chat", "run_browser", "run_desktop"]:
    decision = state.get("supervisor_decision") or {}
    if not decision.get("run_agent"):
        return "chat"
    agent = decision.get("agent")
    goal = (state.get("goal") or "").strip()
    if not goal:
        return "chat"
    if agent == "browser":
        return "run_browser"
    if agent == "desktop":
        return "run_desktop"
    return "chat"


def create_router_graph():
    """Build the graph: start → [chat | supervisor] → [chat | run_browser | run_desktop] → END."""
    builder = StateGraph(RouterState)

    builder.add_node("supervisor", _supervisor_node)
    builder.add_node("chat", _chat_node)
    builder.add_node("run_browser", _run_browser_node)
    builder.add_node("run_desktop", _run_desktop_node)

    builder.add_conditional_edges(
        "__start__",
        _route_after_start,
        path_map={"chat": "chat", "supervisor": "supervisor"},
    )
    builder.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        path_map={"chat": "chat", "run_browser": "run_browser", "run_desktop": "run_desktop"},
    )
    builder.add_edge("chat", END)
    builder.add_edge("run_browser", END)
    builder.add_edge("run_desktop", END)

    return builder.compile()
