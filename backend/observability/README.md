# Observability: skills → logs → evals → optimization (per model)

Each **model** (OpenAI, xAI) is traced and evaluated independently.

## Trace logging (automatic)

- Every chat/agent run is logged to `jarvis-observability/traces/trace.jsonl`.
- Fields: `provider`, `route` (chat | run_browser | run_desktop), `message`, `reply`, `success`, `error`, `duration_sec`, `token_input`, `token_output`.
- **Success rates, tokens, errors** can be aggregated per model via `GET /observability/traces` or `observability.optimize.aggregate_trace_stats()`.

## Evals (multi-turn, from logs)

1. **Generate evals from logs** (LLM-based):  
   `POST /observability/evals/generate?num_traces=30&num_cases=5`  
   Uses recent trace logs to create multi-turn eval cases (coherence / task chains).

2. **Run evals for all models**:  
   `POST /observability/evals/run?case_limit=20`  
   Runs each eval case with both OpenAI and xAI; records **pass@1** per provider.

3. **List cases/runs**:  
   `GET /observability/evals/cases`, `GET /observability/evals/runs`.

## Optimization (periodic)

- **Run optimization step**:  
  `POST /observability/optimization/run`  
  Aggregates traces + eval runs → per-model success rate, eval pass rate, and simple **suggestions** (e.g. “success rate &lt; 0.8”, “benchmark gap between models”).

- **Read latest stats**:  
  `GET /observability/optimization`  
  Returns last run’s `trace_stats`, `eval_pass_at_1`, and `suggestions`.

## HumanEval benchmark (optional)

- `POST /observability/human-eval?max_problems=5`  
  Runs HumanEval-style code-gen benchmark per model. Requires `datasets` and the HumanEval dataset; otherwise returns a stub with install instructions.

## Loop corruption mitigation

- **Guards** in browser and desktop agents: if the same action repeats 3 times in a row, the loop stops early (“Loop guard: repeated action; stopping.”).
- Reduces runaway and degenerate loops.

## Apps (usage patterns)

- **Code gen debug**: enable extra tracing and run evals on code-related goals; use HumanEval for pass@k.
- **Adaptive tutor**: use multi-turn evals for coherence; curriculum = ordered eval difficulty.
- **Personalized**: use optimization stats per user/session to tune prompt or params (extend optimization layer to store per-user suggestions).
