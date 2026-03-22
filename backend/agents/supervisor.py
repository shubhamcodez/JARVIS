"""Supervisor agent: decides whether to run an agent at all, which one (browser/desktop/coding), and the next steps."""
from __future__ import annotations

import json
import re
from typing import Optional

from agents.models import get_llm_client

_SUPERVISOR_SYSTEM = """You are the JARVIS supervisor. You decide how to handle each user message.

You have four options:
1. **chat** – Answer with conversation only (questions, explanations, summarize, chat). No code execution or computer control.
2. **browser** – Something in a web browser (open a URL, search the web, navigate a site, fill a form online).
3. **desktop** – Control the **GUI**: clicking the screen, taskbar, opening apps by clicking, typing into visible windows. Use ONLY for tasks that require seeing or manipulating the desktop UI.
4. **coding** – Run **Python / computation in the sandbox**: execute a script, calculate factorial or math, algorithms, data transforms, "run this code", `.py` files as a programming task. **NOT** desktop automation (do NOT use desktop to open File Explorer and run python.exe). If the task is programming or calculation, use **coding**, not desktop.

Reply with ONLY a JSON object, no markdown or other text. Use this exact shape:
{
  "run_agent": true or false,
  "agent": "browser" or "desktop" or "coding" or null,
  "goal": "one clear sentence describing the task" or null,
  "reasoning": "one sentence why you chose this",
  "next_steps": "short list of steps I will take"
}

Rules:
- Questions, hello, explain, summarize (no action): run_agent false, agent null, goal null.
- Web/URL/search in browser: run_agent true, agent "browser".
- **Programming / run Python / script / factorial / calculate with code / execute code**: run_agent true, agent **"coding"** — never "desktop" for these.
- Desktop only when the user clearly needs **mouse/keyboard on their screen** (e.g. "click the Start menu", "open Excel from the taskbar").
- Be decisive. Output only valid JSON."""


def _heuristic_coding_task(message: str) -> Optional[dict]:
    """
    Strong signals for programmatic work; avoids sending "run a python script" to the desktop agent.
    Skips when the message looks like a URL-first browser task.
    """
    m = (message or "").strip()
    if not m:
        return None
    low = m.lower()
    if re.search(r"https?://\S+", low):
        return None
    # Browser-y phrases that mention python in URL context
    if "python.org" in low and "open" in low:
        return None

    signals: list[tuple[str, bool]] = [
        ("python script", True),
        ("execute a python", True),
        ("execute python", True),
        ("run a python", True),
        ("run python script", True),
        ("run the script", True),
        ("factorial", True),
        ("write python", True),
        ("python code", True),
        ("in the sandbox", True),
        ("coding agent", True),
        (".py", "run" in low or "execute" in low),
        ("calculate", "python" in low),
        ("compute", "python" in low),
    ]
    for phrase, ok in signals:
        if not ok:
            continue
        if phrase in low:
            return {
                "run_agent": True,
                "agent": "coding",
                "goal": m,
                "reasoning": "Heuristic: task is code/computation (sandbox), not GUI desktop control.",
                "next_steps": "1. Generate Python for the goal 2. Run in sandbox 3. Return output",
            }
    return None


def supervisor_decision(api_key: str, provider: str, user_message: str) -> dict:
    """
    Ask the supervisor LLM to decide: chat vs browser vs desktop vs coding agent.
    Returns dict with: run_agent (bool), agent ("browser"|"desktop"|"coding"|null), goal (str|null),
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

    hinted = _heuristic_coding_task(user_message)
    if hinted:
        g = (hinted.get("goal") or user_message).strip()
        return {
            "run_agent": True,
            "agent": "coding",
            "goal": g,
            "reasoning": str(hinted.get("reasoning") or ""),
            "next_steps": str(hinted.get("next_steps") or ""),
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
    if agent not in ("browser", "desktop", "coding"):
        agent = None
    if not run_agent:
        agent = None
    goal = (out.get("goal") or "").strip() or None
    if not goal and agent:
        goal = user_message

    reasoning = (out.get("reasoning") or "").strip()
    next_steps = (out.get("next_steps") or "").strip()

    # LLM sometimes picks desktop for pure coding tasks; never automate the GUI for these.
    if agent == "desktop":
        low = user_message.lower()
        coding_override = any(
            k in low
            for k in (
                "factorial",
                "python script",
                "execute python",
                "run python",
                "run a script",
                "write a program",
                "write python",
                "coding task",
                "in python",
                "sandbox",
            )
        ) or (".py" in low and ("run" in low or "execute" in low))
        if coding_override:
            agent = "coding"
            reasoning = (reasoning + " " if reasoning else "") + "(Rerouted to coding agent: programmatic task.)"

    return {
        "run_agent": run_agent and agent is not None and bool(goal),
        "agent": agent,
        "goal": goal,
        "reasoning": reasoning.strip(),
        "next_steps": next_steps,
    }
