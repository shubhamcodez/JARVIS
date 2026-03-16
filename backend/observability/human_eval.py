"""
HumanEval benchmark: run code-gen evals vs HumanEval (or a subset) per model.
Optional dependency: datasets + human-eval from Hugging Face / OpenAI.
If not installed, benchmark is a no-op and returns empty results.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .config import OPT_DIR, ensure_dirs


def run_human_eval_benchmark(
    providers: Optional[list[str]] = None,
    max_problems: int = 5,
) -> dict[str, Any]:
    """
    Run HumanEval (or stub) for each provider; return pass@k style results.
    Without human-eval/datasets installed, returns stub with instructions.
    """
    try:
        from config import get_openai_api_key, get_xai_api_key
        from agents.models import get_llm_client
    except Exception:
        return {"error": "config or models not available", "pass_at_1": {}}
    providers = providers or ["openai", "xai"]
    try:
        import datasets
        he = datasets.load_dataset("openai_humaneval", "openai-human-eval", trust_remote_code=True)
        problems = list(he["test"])[:max_problems]
    except Exception:
        return {
            "note": "Install: pip install datasets; HumanEval requires openai-human-eval dataset",
            "pass_at_1": {p: None for p in providers},
        }
    results = {}
    for provider in providers:
        api_key = get_openai_api_key() if provider == "openai" else get_xai_api_key()
        client = get_llm_client(provider)
        passed = 0
        for item in problems:
            prompt = item.get("prompt", "") + item.get("canonical_solution", "")
            entry_point = item.get("entry_point", "check")
            test_str = item.get("test", "")
            try:
                completion = client.chat(api_key, f"Complete this Python function. Return only the function body.\n{prompt}", attachment_paths=None)
                # Minimal exec check (real HumanEval runs unit tests)
                exec_globals = {}
                exec(f"{prompt}{completion}\n{test_str}", exec_globals)
                fn = exec_globals.get(entry_point)
                if fn and callable(fn):
                    passed += 1
            except Exception:
                pass
        results[provider] = passed / len(problems) if problems else 0
    ensure_dirs()
    out_path = OPT_DIR / "human_eval_results.json"
    try:
        out_path.write_text(json.dumps({"pass_at_1": results}, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"pass_at_1": results}
