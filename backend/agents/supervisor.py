"""Supervisor agent: decides whether to run an agent at all, which one (browser/desktop), and the next steps."""
from __future__ import annotations

import json
import re
from typing import Optional

from agents.models import get_llm_client

_SUPERVISOR_SYSTEM = """You are the JARVIS supervisor. You decide how to handle each user message.

You have three options:
1. **chat** – Answer with conversation only (questions, explanations, summarize, chat). No computer action.
2. **browser** – The user wants something done in a web browser (open a URL, search, navigate, fill a form on a website). Use when the task involves the web or a specific URL.
3. **desktop** – The user wants something done on their computer outside the browser (open an app, click on screen, type in an app, use the taskbar). Use when the task is about local apps or screen control.

Reply with ONLY a JSON object, no markdown or other text. Use this exact shape:
{
  "run_agent": true or false,
  "agent": "browser" or "desktop" or null,
  "goal": "one clear sentence describing the task" or null,
  "reasoning": "one sentence why you chose this",
  "next_steps": "short list of steps I will take (e.g. 1. Open URL 2. Find search box ...)"
}

Rules:
- If the user is just asking a question, saying hello, or wants explanation/summary: run_agent false, agent null, goal null. Set reasoning and next_steps to empty or a brief note.
- If they want a web/browser action (open site, search google, go to URL): run_agent true, agent "browser", goal one sentence, fill reasoning and next_steps.
- If they want a local/desktop action (open Chrome the app, click something on screen): run_agent true, agent "desktop", goal one sentence, fill reasoning and next_steps.
- Be decisive. Output only valid JSON."""


def supervisor_decision(api_key: str, provider: str, user_message: str) -> dict:
    """
    Ask the supervisor LLM to decide: chat vs browser vs desktop agent.
    Returns dict with: run_agent (bool), agent ("browser"|"desktop"|null), goal (str|null),
    reasoning (str), next_steps (str).
    """
    user_message = (user_message or "").strip()
    if not user_message:
        return {
            "run_agent": False,
            "agent": None,
            "goal": None,
            "reasoning": "",
            "next_steps": "",
        }

    mod = get_llm_client(provider)
    client = mod._client(api_key)
    model = getattr(mod, "CHAT_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SUPERVISOR_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        max_tokens=400,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "run_agent": False,
            "agent": None,
            "goal": None,
            "reasoning": "Could not parse supervisor response.",
            "next_steps": "",
        }

    run_agent = bool(out.get("run_agent"))
    agent = out.get("agent")
    if agent not in ("browser", "desktop"):
        agent = None
    if not run_agent:
        agent = None
    goal = (out.get("goal") or "").strip() or None
    if not goal and agent:
        goal = user_message
    return {
        "run_agent": run_agent and agent is not None and bool(goal),
        "agent": agent,
        "goal": goal,
        "reasoning": (out.get("reasoning") or "").strip(),
        "next_steps": (out.get("next_steps") or "").strip(),
    }
