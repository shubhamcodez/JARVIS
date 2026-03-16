"""Planning and step-outcome evaluation for browser and desktop agents."""
from __future__ import annotations

import json
import re
from typing import Literal

from agents.models import get_llm_client


def get_plan(
    goal: str,
    agent_type: Literal["browser", "desktop"],
    api_key: str,
    provider: str,
) -> list[str]:
    """
    Ask the LLM for a short list of steps to achieve the goal.
    Returns a list of step descriptions (e.g. ["Open URL", "Find search box", "Type query", "Submit"]).
    """
    if not (goal or "").strip():
        return ["Complete the user's request."]

    system = """You are a task planner for an automation agent. The agent will execute steps one by one.

Given the user's goal, output a short, ordered list of concrete steps (3–8 steps). Each step should be one line.
Output ONLY a JSON array of strings, no markdown or explanation. Example:
["Open the target URL", "Locate the search input", "Type the search query", "Click search or press Enter", "Verify results"]

Keep steps high-level but actionable. For browser: navigation, finding elements, typing, clicking, scrolling. For desktop: locating UI, clicking, typing, opening apps."""

    user = f"Agent type: {agent_type}\nGoal: {goal.strip()}\n\nReply with ONLY the JSON array of step strings."

    mod = get_llm_client(provider)
    client = mod._client(api_key)
    model = getattr(mod, "CHAT_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=400,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        steps = json.loads(raw)
        if isinstance(steps, list):
            return [str(s).strip() for s in steps if str(s).strip()]
        return [goal.strip()]
    except (json.JSONDecodeError, TypeError):
        return [goal.strip()]


def evaluate_step_outcome(
    goal: str,
    plan_step: str,
    result: str | None,
    plan: list[str],
    plan_index: int,
    api_key: str,
    provider: str,
) -> dict:
    """
    Evaluate whether the last step succeeded and how to proceed.
    Returns {"success": bool, "decision": "retry"|"next"|"back", "reason": str}.
    """
    result = (result or "").strip()
    plan_step = (plan_step or "").strip()

    system = """You evaluate the outcome of one automation step and decide what to do next.

Given:
- The user's goal
- The current plan step that was just executed
- The result of that step (success message or error)
- The full plan and current position

Reply with ONLY a JSON object:
{"success": true or false, "decision": "retry"|"next"|"back", "reason": "one short sentence"}

Rules:
- success: true if the step achieved its intent (e.g. clicked, typed, navigated); false if error or wrong outcome.
- decision "retry": step failed or unclear; try the same step again (e.g. click missed, type failed).
- decision "next": step succeeded or we should move on; go to the next plan step.
- decision "back": we went the wrong way or need to undo; go back to the previous plan step and try again.
- Prefer "next" when the result looks good; "retry" when there was an error or nothing happened; "back" when we navigated wrong or need to correct."""

    plan_preview = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan))
    user = f"Goal: {goal}\n\nCurrent plan step ({plan_index + 1}/{len(plan)}): {plan_step}\n\nResult: {result or '(no result)'}\n\nFull plan:\n{plan_preview}\n\nReply with ONLY the JSON object."

    mod = get_llm_client(provider)
    client = mod._client(api_key)
    model = getattr(mod, "CHAT_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=150,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        out = json.loads(raw)
        success = bool(out.get("success"))
        decision = (out.get("decision") or "next").lower()
        if decision not in ("retry", "next", "back"):
            decision = "next"
        reason = str(out.get("reason") or "").strip()
        return {"success": success, "decision": decision, "reason": reason}
    except (json.JSONDecodeError, TypeError):
        # Default: if result has "Error", retry; else next
        return {
            "success": "error" not in (result or "").lower(),
            "decision": "retry" if result and "error" in result.lower() else "next",
            "reason": "Parse failed; defaulting.",
        }
