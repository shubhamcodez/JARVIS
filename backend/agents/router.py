"""Router graph: supervisor decides route → chat | desktop | coding | shell | finance agent."""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from langgraph.graph import END, StateGraph

from .state import RouterState
from tools.runner import run_tools_for_turn


async def _supervisor_node(state: RouterState) -> RouterState:
    from .supervisor import supervisor_decision

    message = (state.get("message") or "").strip()
    api_key = state["api_key"]
    provider = state.get("provider") or "openai"
    decision = await asyncio.to_thread(supervisor_decision, api_key, provider, message)
    goal = (decision.get("goal") or message).strip()
    return {"supervisor_decision": decision, "goal": goal}


async def _chat_node(state: RouterState) -> RouterState:
    from agents.models import get_llm_client

    from memory import get_memory_store, run_retrieval_pipeline
    from memory.chat_log import read_chat_log

    api_key = state["api_key"]
    provider = state.get("provider") or "openai"
    client = get_llm_client(provider)
    message = (state.get("message") or "").strip()
    paths = state.get("attachment_paths") or []
    if not message and paths:
        message = "Please summarize or answer based on the attached documents."

    chat_id = state.get("chat_id") or ""
    # Load conversation history (frontend already appended current user message)
    recent_turns = read_chat_log(chat_id) if chat_id else []
    max_history = 40
    history = recent_turns[-max_history:] if recent_turns else None

    # Retrieval: current conversation → query → vector search → inject as system context
    memory_context = ""
    try:
        from config import get_openai_api_key

        store = get_memory_store()
        if len(store) > 0:
            openai_api_key = get_openai_api_key()
            task_state = {"goal": state.get("goal"), "route": "chat"}
            memory_context, _ = run_retrieval_pipeline(
                store,
                openai_api_key,
                current_message=message,
                recent_turns=recent_turns,
                task_state=task_state,
                top_k=10,
                include_raw_top_n=3,
            )
    except Exception:
        pass

    # Tool calls: every turn has conversation; then run applicable tools (weather, etc.) and inject results
    tool_system, tool_used = run_tools_for_turn(message or "", recent_turns=recent_turns or [])
    if tool_system:
        memory_context = (memory_context or "") + "\n\n" + tool_system

    # Build system content (memory + tool) and call with history so the model sees the conversation
    system_content = (memory_context or "").strip() or None
    reply = await asyncio.to_thread(
        client.chat,
        api_key,
        message or "Hello.",
        paths if paths else None,
        history,
        system_content,
    )
    out: RouterState = {"reply": reply, "route": "chat"}
    if tool_used:
        out["tool_used"] = tool_used
    return out


def _emit_supervisor_step(state: RouterState) -> None:
    """Emit supervisor's next_steps as step 0 so the UI shows the plan."""
    on_step = state.get("on_step")
    if not on_step:
        return
    decision = state.get("supervisor_decision") or {}
    reasoning = decision.get("reasoning") or ""
    next_steps = decision.get("next_steps") or "Running agent."
    on_step(0, reasoning, "supervisor", next_steps, None, False)


async def _run_desktop_node(state: RouterState) -> RouterState:
    from .desktop_agent import run_desktop_agent

    _emit_supervisor_step(state)
    goal = state.get("goal") or ""
    on_step = state.get("on_step")
    api_key = state["api_key"]
    provider = state.get("provider") or "openai"
    reply = await asyncio.to_thread(run_desktop_agent, goal, 10, on_step, api_key=api_key, provider=provider)
    return {"reply": reply, "route": "run_desktop"}


async def _run_coding_node(state: RouterState) -> RouterState:
    from .coding_agent import run_coding_agent

    _emit_supervisor_step(state)
    goal = state.get("goal") or ""
    on_step = state.get("on_step")
    api_key = state["api_key"]
    provider = state.get("provider") or "openai"
    reply, tool_used = await asyncio.to_thread(
        run_coding_agent, goal, on_step, api_key, provider
    )
    out: RouterState = {"reply": reply, "route": "run_coding"}
    if tool_used:
        out["tool_used"] = tool_used
    return out


async def _run_shell_node(state: RouterState) -> RouterState:
    from .shell_agent import run_shell_agent

    _emit_supervisor_step(state)
    goal = state.get("goal") or ""
    on_step = state.get("on_step")
    api_key = state["api_key"]
    provider = state.get("provider") or "openai"
    reply, tool_used = await asyncio.to_thread(
        run_shell_agent, goal, on_step, api_key, provider
    )
    out: RouterState = {"reply": reply, "route": "run_shell"}
    if tool_used:
        out["tool_used"] = tool_used
    return out


async def _run_finance_node(state: RouterState) -> RouterState:
    from .finance_agent import run_finance_agent

    _emit_supervisor_step(state)
    goal = state.get("goal") or ""
    on_step = state.get("on_step")
    api_key = state["api_key"]
    provider = state.get("provider") or "openai"
    reply, tool_used = await asyncio.to_thread(
        run_finance_agent, goal, on_step, api_key, provider
    )
    out: RouterState = {"reply": reply, "route": "run_finance"}
    if tool_used:
        out["tool_used"] = tool_used
    return out


def _route_after_start(state: RouterState) -> Literal["chat", "supervisor"]:
    message = (state.get("message") or "").strip()
    paths = state.get("attachment_paths") or []
    if not message and paths:
        return "chat"
    return "supervisor"


def _route_after_supervisor(
    state: RouterState,
) -> Literal["chat", "run_desktop", "run_coding", "run_shell", "run_finance"]:
    decision = state.get("supervisor_decision") or {}
    if not decision.get("run_agent"):
        return "chat"
    agent = decision.get("agent")
    goal = (state.get("goal") or "").strip()
    if not goal:
        return "chat"
    if agent == "desktop":
        return "run_desktop"
    if agent == "coding":
        return "run_coding"
    if agent == "shell":
        return "run_shell"
    if agent == "finance":
        return "run_finance"
    return "chat"


def create_router_graph():
    """Build the graph: start → [chat | supervisor] → [chat | desktop | coding | shell | finance] → END."""
    builder = StateGraph(RouterState)

    builder.add_node("supervisor", _supervisor_node)
    builder.add_node("chat", _chat_node)
    builder.add_node("run_desktop", _run_desktop_node)
    builder.add_node("run_coding", _run_coding_node)
    builder.add_node("run_shell", _run_shell_node)
    builder.add_node("run_finance", _run_finance_node)

    builder.add_conditional_edges(
        "__start__",
        _route_after_start,
        path_map={"chat": "chat", "supervisor": "supervisor"},
    )
    builder.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        path_map={
            "chat": "chat",
            "run_desktop": "run_desktop",
            "run_coding": "run_coding",
            "run_shell": "run_shell",
            "run_finance": "run_finance",
        },
    )
    builder.add_edge("chat", END)
    builder.add_edge("run_desktop", END)
    builder.add_edge("run_coding", END)
    builder.add_edge("run_shell", END)
    builder.add_edge("run_finance", END)

    return builder.compile()
