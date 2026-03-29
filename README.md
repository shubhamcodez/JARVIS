# Socrates (Formerly JARVIS)

Assistant that can chat, control the **desktop** (screenshot + vision + pyautogui—including your on-screen browser), run **sandboxed Python**, optional **host shell** (opt-in), and **market data / analysis** via **yfinance** (finance agent). Routes via a supervisor LLM; supports OpenAI and xAI (Grok).

---

## Core idea: self-improving agents through evals

The agent improves over time by **looping through evals** and turning results into **prompt and code changes**:

1. **Trace every run** — Each chat and agent run is logged (provider, route, success, tokens, errors) to `jarvis-observability/traces/`.
2. **Generate evals from logs** — An LLM turns recent traces into multi-turn evaluation cases (coherence, task completion). Stored in `jarvis-observability/evals/`.
3. **Run evals for all models** — Each case is run with both OpenAI and xAI; optional LLM judge scores replies. Pass@1 per model is recorded.
4. **Optimization step** — Aggregates trace stats + eval pass rates, then asks an LLM for:
   - **Prompt modification instructions**: what to add or change in the supervisor, desktop, coding, shell, finance, or chat prompts (with reasons).
   - **Code addition suggestions**: which file and what logic/code to add (e.g. retries, validation), with reasons.

You (or a future automation layer) apply those instructions and suggestions; the next runs and evals reflect the improvements. So: **evals → scores → optimization → prompt/code suggestions → apply → better agents**.

---

## Memory architecture (planned)
Supermemory launches an opensource 98% memory retrieval success framework.
