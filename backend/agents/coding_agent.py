"""Coding agent: LLM writes Python for the goal, runs it in the sandbox, returns output (no GUI)."""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from agents.models import chat_completion_limit_kwargs, get_llm_client, should_omit_temperature
from tools.python_sandbox import extract_python_fences, run_sandboxed_python

_CODING_GEN_SYSTEM = """You are JARVIS's coding agent. The user gave a task that should be solved with Python code running in a secure sandbox—not by clicking the desktop.

**Role vs finance agent:** The finance agent fetches market **data** and short factual/market commentary. **You** run **code**: statistics, transforms, simulations, and **plots**. If they want charts, regressions, correlations, backtests, or custom analysis on prices/returns, do it here with numpy/pandas/matplotlib/yfinance as needed.

Output ONLY a JSON object, no markdown fences, with exactly one key:
  "code": "<python source>"

Rules for the code:
- Allowed imports (stdlib + sandbox): math, json, itertools, functools, collections, statistics, datetime, decimal, fractions, string, random, re, operator, copy, io, base64, csv, hashlib, typing, warnings, plus **numpy**, **pandas**, **matplotlib**, **yfinance** and their usual dependencies (already whitelisted).
- **Matplotlib:** the sandbox sets a headless backend; still call `import matplotlib; matplotlib.use("Agg")` before `pyplot` if you use plots. Save figures to a buffer and **print base64** or print summary stats — there is no GUI; stdout text is what the user sees.
- **yfinance:** OK for pulling `Ticker(...).history(...)` or `fast_info` inside your analysis script when the task needs live series.
- No `open()`, no `os`/`sys`/`subprocess`, no `input()`. Print answers with `print()`.
- Keep code focused; prefer small readable steps.

Example for "factorial of 10":
{"code": "import math\\nprint(math.factorial(10))"}
"""


def _parse_code_from_llm(raw: str) -> Optional[str]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        obj = json.loads(text)
        c = obj.get("code")
        if isinstance(c, str) and c.strip():
            return c.strip()
    except json.JSONDecodeError:
        pass
    blocks = extract_python_fences(raw or "")
    if blocks:
        return "\n\n".join(blocks).strip()
    return None


def run_coding_agent(
    goal: str,
    on_step: Optional[Callable] = None,
    api_key: Optional[str] = None,
    provider: str = "openai",
) -> tuple[str, dict]:
    """
    Plan (short) → generate Python → sandbox → optional one retry → formatted reply.
    Returns (reply_text, tool_used for chat log / UI).
    """
    if api_key is None:
        from config import get_llm_api_key

        api_key = get_llm_api_key()

    goal = (goal or "").strip()
    if not goal:
        return "No task provided.", {}

    mod = get_llm_client(provider)
    client = mod._client(api_key)
    model = getattr(mod, "CHAT_MODEL", "gpt-4o")

    plan = (
        "Plan:\n"
        "  1. Interpret the task as computation, data analysis, or visualization (sandbox).\n"
        "  2. Generate Python (stdlib + numpy/pandas/matplotlib/yfinance as needed).\n"
        "  3. Execute in the isolated sandbox and return stdout.\n"
    )
    if on_step:
        on_step(0, plan, "plan", plan, None, False, screenshot_base64=None)

    user_msg = f"Task:\n{goal}\n\nOutput ONLY JSON: {{\"code\": \"...\"}}"

    def call_llm(follow_ups: Optional[list[dict]] = None) -> str:
        messages: list[dict] = [
            {"role": "system", "content": _CODING_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        if follow_ups:
            messages.extend(follow_ups)
        create_kw: dict = {
            "model": model,
            "messages": messages,
            **chat_completion_limit_kwargs(provider, model, 2500),
        }
        if not should_omit_temperature(provider, model):
            create_kw["temperature"] = 0.2
        resp = client.chat.completions.create(**create_kw)
        return (resp.choices[0].message.content or "").strip()

    raw = call_llm()
    code = _parse_code_from_llm(raw)
    if not code:
        reply = (
            f"Coding task (goal: {goal}).\n\n"
            "I could not extract valid Python from the model output. Raw response (truncated):\n"
            f"{raw[:1500]}"
        )
        tool_used = {"name": "python_sandbox", "input": goal[:500], "result": raw[:2000]}
        if on_step:
            on_step(1, "Parse failed", "error", raw[:200], None, True, screenshot_base64=None)
        return reply, tool_used

    if on_step:
        on_step(
            1,
            "Generated Python; executing in sandbox.",
            "sandbox",
            code[:500] + ("…" if len(code) > 500 else ""),
            None,
            False,
            screenshot_base64=None,
        )

    result = run_sandboxed_python(code, timeout_sec=45.0)
    if not result.get("ok"):
        fix_msg = (
            "Your previous code failed in the sandbox. Fix it.\n\n"
            f"Code was:\n```\n{code[:3000]}\n```\n\n"
            f"Sandbox result:\n{json.dumps(result, indent=2)[:4000]}\n\n"
            'Output ONLY JSON with key "code".'
        )
        raw2 = call_llm(
            [
                {"role": "assistant", "content": raw[:8000]},
                {"role": "user", "content": fix_msg},
            ]
        )
        code2 = _parse_code_from_llm(raw2)
        if code2:
            code = code2
            result = run_sandboxed_python(code, timeout_sec=45.0)

    tool_used = {
        "name": "python_sandbox",
        "input": code[:4000] + ("…" if len(code) > 4000 else ""),
        "result": json.dumps(result, ensure_ascii=False)[:8000],
    }

    stdout = (result.get("stdout") or "").strip()
    stderr = (result.get("stderr") or "").strip()
    if result.get("ok"):
        body = f"**Sandbox stdout:**\n```\n{stdout or '(no output)'}\n```"
        if stderr:
            body += f"\n**stderr:**\n```\n{stderr}\n```"
        reply = (
            f"Coding task (goal: {goal}).\n\n"
            f"{body}\n\n"
            "_Executed in the restricted Python sandbox (no desktop automation)._"
        )
        if on_step:
            on_step(2, "Sandbox run succeeded.", "done", stdout[:300], stdout, True, screenshot_base64=None)
    else:
        err = result.get("error") or "unknown error"
        tb = (result.get("traceback") or "")[:2000]
        reply = (
            f"Coding task (goal: {goal}).\n\n"
            f"Sandbox run failed: **{err}**\n\n"
            f"```\n{tb}\n```"
        )
        if on_step:
            on_step(2, f"Sandbox failed: {err}", "done", err, None, True, screenshot_base64=None)

    return reply, tool_used
