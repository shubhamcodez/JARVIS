"""
After each successful conversation turn: optionally run eval case generation and optimization
suggestions in the background. Never applies code—only appends eval cases and writes
optimization_stats.json (prompt/code suggestions for humans).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_last_eval_gen = 0.0
_last_opt = 0.0


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def schedule_post_turn_observability() -> None:
    """
    Fire-and-forget background work after a trace has been written for this turn.
    Respects cooldowns and JARVIS_AUTO_* env vars.
    """
    if not _env_bool("JARVIS_AUTO_OBSERVABILITY", True):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_post_turn_observability_task())


async def _post_turn_observability_task() -> None:
    await asyncio.to_thread(_run_post_turn_sync)


def _run_post_turn_sync() -> None:
    global _last_eval_gen, _last_opt
    now = time.time()
    eval_cd = _env_float("JARVIS_AUTO_EVAL_COOLDOWN_SEC", 60.0)
    opt_cd = _env_float("JARVIS_AUTO_OPT_COOLDOWN_SEC", 600.0)

    do_eval = False
    do_opt = False
    with _lock:
        if _env_bool("JARVIS_AUTO_EVAL_GEN", True) and (now - _last_eval_gen >= eval_cd):
            _last_eval_gen = now
            do_eval = True
        if _env_bool("JARVIS_AUTO_OPTIMIZATION_SUGGESTIONS", True) and (now - _last_opt >= opt_cd):
            _last_opt = now
            do_opt = True

    if do_eval:
        try:
            from .eval_gen import generate_evals_from_logs

            generate_evals_from_logs(
                num_traces=_env_int("JARVIS_AUTO_EVAL_NUM_TRACES", 15),
                num_cases=_env_int("JARVIS_AUTO_EVAL_NUM_CASES", 2),
                meta_source="eval_gen_auto",
            )
        except Exception as e:
            logger.debug("auto eval gen failed: %s", e)

    if do_opt:
        try:
            from .optimize import run_optimization_step

            run_optimization_step()
        except Exception as e:
            logger.debug("auto optimization step failed: %s", e)
