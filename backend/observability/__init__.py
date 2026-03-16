"""
Observability: skills → trace logs → eval generation → auto-optimization.
- Trace: success rates, tokens, errors per run (per model).
- Evals: multi-turn cases, LLM-generated from logs; coherence/task scoring.
- Optimization: prompt/param tuning, pass@k, Bayesian/RL on logs.
- Guards: loop corruption mitigation.
"""
from .trace import trace_log, get_trace_log_path, list_traces
from .evals import EvalCase, EvalRun, load_eval_cases, save_eval_cases, append_eval_run
from .guards import check_loop_corruption

__all__ = [
    "trace_log",
    "get_trace_log_path",
    "list_traces",
    "EvalCase",
    "EvalRun",
    "load_eval_cases",
    "save_eval_cases",
    "append_eval_run",
    "check_loop_corruption",
]
