# Observability: skills → logs → evals → optimization (per model)

Each **model** (OpenAI, xAI) is traced and evaluated independently.

## Trace logging (automatic)

- Every chat/agent run is logged to `jarvis-observability/traces/trace.jsonl`.
- Fields: `provider`, `route` (chat | run_desktop | run_coding | run_shell | run_finance), `message`, `reply`, `success`, `error`, `duration_sec`, `token_input`, `token_output`.
- **Streaming chat** (`/chat/send-message/stream` on the chat path) now also writes a trace row when the stream completes.
- **Success rates, tokens, errors** can be aggregated per model via `GET /observability/traces` or `observability.optimize.aggregate_trace_stats()`.

## Automatic post-turn loop (eval cases + suggestion files)

After each **successful** turn (trace written), the backend schedules **background** work (does not block the HTTP response):

1. **Eval generation** (default **on**): runs the same LLM-based generator as `POST /observability/evals/generate`, using recent traces. New cases are **appended** to `eval_cases.jsonl` with `meta.source = "eval_gen_auto"`. Nothing is executed against your codebase.
2. **Optimization step** (default **on**): runs `run_optimization_step()` which refreshes `optimization_stats.json` with trace/eval aggregates plus **prompt_modification_instructions** and **code_addition_suggestions** (text only—**no auto-apply**).

**Environment variables** (all optional):

| Variable | Default | Meaning |
|----------|---------|---------|
| `JARVIS_AUTO_OBSERVABILITY` | `1` | Master switch for the background task |
| `JARVIS_AUTO_EVAL_GEN` | `1` | Generate eval cases from logs |
| `JARVIS_AUTO_EVAL_COOLDOWN_SEC` | `60` | Min seconds between eval generations |
| `JARVIS_AUTO_EVAL_NUM_TRACES` | `15` | Traces sampled for each auto generation |
| `JARVIS_AUTO_EVAL_NUM_CASES` | `2` | Max cases appended per run |
| `JARVIS_AUTO_OPTIMIZATION_SUGGESTIONS` | `1` | Refresh optimization JSON with LLM suggestions |
| `JARVIS_AUTO_OPT_COOLDOWN_SEC` | `600` | Min seconds between optimization runs (10 min) |

Set any `*_AUTO_*` to `0` / `false` / `off` to disable that piece.

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

- **Guards** in the desktop agent: if the same action repeats 3 times in a row, the loop stops early (“Loop guard: repeated action; stopping.”).
- Reduces runaway and degenerate loops.

## Apps (usage patterns)

- **Code gen debug**: enable extra tracing and run evals on code-related goals; use HumanEval for pass@k.
- **Adaptive tutor**: use multi-turn evals for coherence; curriculum = ordered eval difficulty.
- **Personalized**: use optimization stats per user/session to tune prompt or params (extend optimization layer to store per-user suggestions).
