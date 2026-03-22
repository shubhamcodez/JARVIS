# JARVIS

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

Structured memory so the model can use past chats, docs, and code without dumping everything into the prompt.

**Four stores**

- **Raw chunk store** — `chunk_id`, `content`, `source_type` (chat, code, doc, note), `source_id`, `created_at`, `version`, `metadata`. Persistence for all ingested content.
- **Vector index** (e.g. **Chroma**) — `chunk_id`, `embedding`, lightweight metadata filters. Fast semantic retrieval.
- **Summary store** — `summary_id`, `chunk_id` or `parent_id`, short summary, structured facts/entities/decisions. Prompt-ready compression.
- **Working state store** — Current task, active files, recent decisions, unresolved questions, last retrieved memory set. Per-session continuity.

**Chunking**

- **Chats:** 1–5 message windows, preserve speaker turns, no split across a decision. Metadata: `conversation_id`, `turn_range`, intent, decisions, open loops.
- **Docs:** Headings/sections first, then paragraph windows; ~10–20% overlap.
- **Code:** By file, class, function, method, config/schema block (not plain text). Metadata: `file_path`, `symbol_name`, `symbol_type`, imports/exports, line range, repo version.

**Flow**

- **Ingestion:** Parse → chunk → enrich metadata → summarize → embed → write to raw store, vector DB, summary store.
- **Retrieval:** Query understanding → hybrid retrieval (vector + keyword + structural) → rerank → select summaries + raw chunks.
- **Prompt assembly:** System + current request + task state + retrieved summaries + selected chunks, with token budgets (e.g. summaries first, raw chunks selectively).
- **After each turn:** Update working state; write back only important turns (decisions, facts, artifacts) to avoid clutter.

This gives persistence, fast retrieval, prompt-ready summaries, and current-session continuity. Chroma is the intended vector DB for the MVP.
