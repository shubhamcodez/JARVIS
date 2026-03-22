"""
Trace logging: every agent/chat run logs provider, route, message, reply, steps, success, error, duration, token estimates.
Success rates and token/error stats can be aggregated per model.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from .config import TRACES_DIR, ensure_dirs

TRACE_FILE = "trace.jsonl"
_MAX_LINE = 100_000  # cap lines per file, then rotate


def _trace_path() -> Path:
    ensure_dirs()
    return TRACES_DIR / TRACE_FILE


def get_trace_log_path() -> str:
    return str(_trace_path())


def _estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token for English."""
    return max(0, (len(text or "") + 3) // 4)


def trace_log(
    provider: str,
    route: str,
    message: str,
    reply: str,
    success: bool = True,
    error: Optional[str] = None,
    duration_sec: Optional[float] = None,
    step_count: Optional[int] = None,
    token_input: Optional[int] = None,
    token_output: Optional[int] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    Append one trace record. Called after each chat/agent run.
    provider: "openai" | "xai"
    route: "chat" | "run_desktop" | "run_coding" | "run_shell" | "run_finance" | ...
    """
    ensure_dirs()
    path = _trace_path()
    if token_input is None:
        token_input = _estimate_tokens(message)
    if token_output is None:
        token_output = _estimate_tokens(reply)
    record = {
        "ts": time.time(),
        "provider": provider,
        "route": route,
        "message": (message or "")[:2000],
        "reply": (reply or "")[:4000],
        "success": success,
        "error": error,
        "duration_sec": duration_sec,
        "step_count": step_count,
        "token_input": token_input,
        "token_output": token_output,
        **(extra or {}),
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def list_traces(limit: int = 500) -> list[dict]:
    """Read latest trace records (newest last in file, so we tail)."""
    path = _trace_path()
    if not path.exists():
        return []
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        return []
    if len(lines) <= limit:
        out = lines
    else:
        out = lines[-limit:]
    result = []
    for line in out:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result
