"""
Run evals for each model: execute multi-turn cases, score coherence/task (LLM judge or heuristics), record pass@k.
"""
from __future__ import annotations

from typing import Optional

from config import get_llm_api_key, get_openai_api_key, get_xai_api_key
from agents.models import get_llm_client

from .evals import EvalCase, EvalRun, load_eval_cases, append_eval_run


JUDGE_SYSTEM = """You are an evaluator. Given a multi-turn conversation (messages + model reply) and an optional rubric/expected outcome, score the reply.
Reply with ONLY a JSON object: {"score": 0.0-1.0, "passed": true|false, "reason": "one sentence"}.
Score for coherence and task completion. If no rubric, use coherence and relevance."""


def _run_case_with_provider(case: EvalCase, provider: str) -> EvalRun:
    """Run one eval case with the given provider; return EvalRun."""
    api_key = get_openai_api_key() if provider == "openai" else get_xai_api_key()
    client = get_llm_client(provider)
    messages = list(case.messages)
    if not messages:
        return EvalRun(case_id=case.id, provider=provider, reply="", error="no messages", passed=False)
    # Build prompt: last user turn is the one we need a reply for
    last_user = None
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    if not last_user:
        # All assistant? Use last content as prompt
        full = "\n".join(f"{m.get('role')}: {m.get('content', '')}" for m in messages)
        prompt = full + "\n\nContinue the conversation as the assistant."
    else:
        prompt = last_user
    try:
        reply = client.chat(api_key, prompt, attachment_paths=None)
    except Exception as e:
        return EvalRun(case_id=case.id, provider=provider, reply="", error=str(e), passed=False)
    # Optional: LLM judge for score (use OpenAI for judge to save cost on eval models)
    score = None
    passed = None
    try:
        judge_key = get_openai_api_key()
        judge_client = get_llm_client("openai")
        judge_prompt = f"{JUDGE_SYSTEM}\n\nMessages: {messages}\n\nModel reply: {reply[:500]}\n\nExpected/rubric: {case.expected or case.rubric or 'N/A'}\n\nReply with ONLY the JSON object."
        raw = judge_client.chat(judge_key, judge_prompt, attachment_paths=None)
        import json
        import re
        raw = re.sub(r"^```(?:json)?\s*", "", (raw or "").strip())
        raw = re.sub(r"\s*```\s*$", "", raw)
        out = json.loads(raw)
        score = float(out.get("score", 0)) if isinstance(out.get("score"), (int, float)) else None
        passed = out.get("passed") if isinstance(out.get("passed"), bool) else None
    except Exception:
        pass
    run = EvalRun(case_id=case.id, provider=provider, reply=reply[:2000], score=score, passed=passed)
    append_eval_run(run)
    return run


def run_evals_for_all_models(
    case_limit: int = 20,
    providers: Optional[list[str]] = None,
) -> list[EvalRun]:
    """Run loaded eval cases for openai and xai; return all EvalRuns. Skips provider if key missing."""
    providers = providers or ["openai", "xai"]
    cases = load_eval_cases(limit=case_limit)
    runs = []
    for case in cases:
        for provider in providers:
            try:
                if provider == "openai":
                    get_openai_api_key()
                else:
                    get_xai_api_key()
                run = _run_case_with_provider(case, provider)
                runs.append(run)
            except Exception:
                continue
    return runs


def pass_at_k(runs: list[dict], k: int = 1) -> dict[str, float]:
    """Given eval runs (list of dicts with provider, passed), compute pass@k per provider."""
    by_provider = {}
    for r in runs:
        p = r.get("provider", "")
        if p not in by_provider:
            by_provider[p] = []
        if r.get("passed") is not None:
            by_provider[p].append(1 if r.get("passed") else 0)
    out = {}
    for p, results in by_provider.items():
        if len(results) == 0:
            out[p] = 0.0
        else:
            out[p] = sum(results) / len(results)
    return out
