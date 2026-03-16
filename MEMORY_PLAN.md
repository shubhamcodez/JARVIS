# Memory feature — implementation plan

Phased implementation of the four-store memory architecture (raw chunk, vector index, summary store, working state) with Chroma, chat chunking, retrieval, prompt assembly, and write-back.

---

## Phase 1: Foundation

### Step 1 — Define schemas
- [ ] **1.1** Pydantic/dataclass models: `Chunk` (chunk_id, content, source_type, source_id, parent_id, created_at, version, metadata), `Summary` (summary_id, chunk_id, parent_id, content, facts, created_at), `TaskState` (session_id, current_goal, active_chunk_ids, recent_decisions, open_questions, last_retrieved_ids, updated_at).
- [ ] **1.2** Source types: `chat`, `code`, `doc`, `note`, `agent_trace`.

### Step 2 — Persistence for raw chunks and working state
- [ ] **2.1** Memory config: directory for DBs (e.g. `jarvis-memory/`), paths for SQLite files.
- [ ] **2.2** Raw chunk store: SQLite table (or JSONL) for chunks; `insert_chunk`, `get_chunk`, `list_chunks_by_source`.
- [ ] **2.3** Working state store: SQLite table keyed by session_id (e.g. chat_id); `get_task_state`, `update_task_state`.

### Step 3 — Chat chunker and ingestion
- [ ] **3.1** Chat chunker: input = list of messages (from chat_log format); output = list of Chunk-like dicts with 1–5 message windows, conversation_id, turn_range; preserve speaker turns; do not split mid-decision (simple: by turn windows).
- [ ] **3.2** Ingestion pipeline: given conversation_id and messages, run chunker → enrich metadata (created_at, source_id) → return list of chunks (no embed yet).

### Step 4 — Vector index (Chroma) and embeddings
- [ ] **4.1** Add dependency: `chromadb` (and optional `tiktoken` for token counting).
- [ ] **4.2** Embeddings module: call OpenAI (or configurable) embedding API; function `embed(text: str) -> list[float]`; batch if needed.
- [ ] **4.3** Chroma collection: create or get collection; metadata: source_type, source_id, conversation_id, turn_range (for chat). Store chunk_id, embedding, metadata.
- [ ] **4.4** Ingest into vector store: after raw chunk store write, embed content → add to Chroma with chunk_id and metadata.

### Step 5 — Retrieval
- [ ] **5.1** Retrieve by query: embed query → Chroma query with top_k and metadata filters (e.g. by conversation_id or source_type) → return list of (chunk_id, content, metadata, distance).
- [ ] **5.2** Optional: get chunk content from raw store by chunk_id if Chroma doesn’t store full content.

### Step 6 — Prompt assembly
- [ ] **6.1** Token budget: configurable slots (e.g. 10% task state, 20% retrieved, 35% raw chunks, 20% response headroom); use tiktoken or rough 4 chars/token.
- [ ] **6.2** Assembly function: inputs = system, current_request, task_state dict, retrieved chunks list; output = single prompt string or structured parts (system + context + request) that stays within budget.
- [ ] **6.3** Format: "Current task: ... Recent decisions: ... Retrieved: [chunk_id] ... Content: ..." so the model sees provenance.

### Step 7 — Wire into request flow and write-back
- [ ] **7.1** Before supervisor (or before chat): load task state by chat_id/session_id; run retrieval with current message as query; assemble context; pass augmented context to supervisor/chat (e.g. as extra system or prefix).
- [ ] **7.2** After reply: update working state (current_goal from supervisor goal or message, recent_decisions, last_retrieved_ids); optionally classify “important” turn (e.g. supervisor chose agent, or user gave clear instruction); if important, run chunker on new messages → ingest (raw + embed + Chroma).
- [ ] **7.3** API: optional query param or header to enable memory (e.g. `?memory=1` or config) so we can ship behind a flag.

---

## Phase 2 (later)

- Summary store: summarize chunks, store separately, retrieve summaries first.
- Hybrid retrieval: keyword (BM25) + vector, then rerank.
- Code chunking: by file/symbol when codebase ingestion is added.
- Reranking model or scoring (semantic + recency + structural).

---

## File layout (backend)

```
memory/
  __init__.py       # re-export chat_log + memory components
  chat_log.py       # existing
  config.py         # memory dir, DB paths (new)
  schemas.py        # Chunk, Summary, TaskState (new)
  chunk_store.py    # raw chunk SQLite (new)
  working_state.py  # task state SQLite (new)
  chunker.py        # chat chunker (new)
  embeddings.py     # embed text, Chroma add/query (new)
  retrieval.py      # top-k retrieval (new)
  prompt_assembly.py # assemble prompt with budget (new)
  write_back.py     # importance check, chunk, ingest (new)
```

---

## Order of implementation

1. **MEMORY_PLAN.md** (this file) — done.
2. **Step 1** — schemas.
3. **Step 2** — config + chunk_store + working_state.
4. **Step 3** — chunker + ingestion (chunker only; ingest step 4).
5. **Step 4** — Chroma + embeddings, wire ingest to write to both raw store and Chroma.
6. **Step 5** — retrieval API.
7. **Step 6** — prompt assembly.
8. **Step 7** — wire into main flow + write-back.
