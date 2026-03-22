"""
LLM-based eval generation from trace logs: sample recent traces, ask LLM to produce multi-turn eval cases (coherence + task chains).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Optional

from config import get_llm_api_key, get_llm_provider
from agents.models import get_llm_client

from .trace import list_traces
from .evals import EvalCase, append_eval_case, load_eval_cases


SYSTEM = """You are an eval designer. Given a sample of real agent/chat logs (message, reply, route), generate multi-turn evaluation cases that resemble real usage and test coherence and task chains.

Output exactly one JSON array of objects. Each object:
- "messages": [{"role": "user"|"assistant", "content": "..."}]  (2-4 turns)
- "expected": one sentence expected outcome or "N/A" for open-ended
- "rubric": short rubric for scoring (coherence, task completion) or null

Generate 2-5 diverse cases. No markdown, no explanation, only the JSON array."""


def _truncate(s: str, n: int = 300) -> str:
    return (s or "")[:n] + ("..." if len(s or "") > n else "")


def generate_evals_from_logs(
    num_traces: int = 30,
    num_cases: int = 5,
    provider: Optional[str] = None,
    meta_source: str = "eval_gen",
) -> list[EvalCase]:
    """
    Use recent trace logs to generate new multi-turn eval cases via LLM.
    Returns list of EvalCase appended to store.
    meta_source: "eval_gen" (manual API) or "eval_gen_auto" (post-turn background).
    """
    provider = provider or get_llm_provider()
    api_key = get_llm_api_key()
    client = get_llm_client(provider)
    traces = list_traces(limit=num_traces)
    if not traces:
        return []
    sample = []
    for t in traces[-num_traces:]:
        sample.append({
            "route": t.get("route"),
            "message": _truncate(t.get("message", ""), 200),
            "reply": _truncate(t.get("reply", ""), 200),
            "success": t.get("success"),
        })
    user = f"Sample logs (last {len(sample)}):\n{json.dumps(sample, ensure_ascii=False)}\n\nGenerate {num_cases} multi-turn eval cases as a JSON array."
    try:
        raw = client.chat(
            api_key, user, attachment_paths=None, system_content=SYSTEM
        )
        # Try to extract JSON array
        raw = (raw or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
        arr = json.loads(raw)
        if not isinstance(arr, list):
            return []
    except (json.JSONDecodeError, TypeError):
        return []
    cases = []
    for i, item in enumerate(arr[:num_cases]):
        if not isinstance(item, dict):
            continue
        messages = item.get("messages") or []
        if not messages:
            continue
        case_id = f"gen-{uuid.uuid4().hex[:8]}"
        case = EvalCase(
            id=case_id,
            messages=messages,
            expected=item.get("expected"),
            rubric=item.get("rubric"),
            meta={"source": meta_source, "provider": provider},
        )
        append_eval_case(case)
        cases.append(case)
    return cases


def list_generated_cases(limit: int = 100) -> list[EvalCase]:
    src = {"eval_gen", "eval_gen_auto"}
    return [c for c in load_eval_cases(limit=limit) if (c.meta or {}).get("source") in src]
