# JARVIS Agent Workflow

End-to-end flow from user message to reply: routing, supervisor, browser/desktop agents, **memory** (planned), and **self-improving evals**.

---

## 1. Entry points

- **POST `/chat/send-message`** (non-streaming): single request/response; used when the client does not need streaming.
- **POST `/chat/send-message/stream`** (streaming): SSE stream; used by the frontend. Can stream chat tokens **or** run the agent and send one final event with the full reply.
- **POST `/chat/response`**: chat-only, no routing (direct LLM reply).

The **provider** (OpenAI or xAI) and **API key** come from `get_llm_provider()` and `get_llm_api_key()` (Settings / `jarvis-llm-provider.txt`).

---

## 2. Streaming path (main UX)

The frontend calls **`sendMessageStream`** → **POST `/chat/send-message/stream`**.

1. **Attachments-only or empty message**  
   - If there is no message but there are attachments, the backend streams a **chat** reply (summarize/answer based on docs).  
   - If the message is empty and no attachments, it streams a reply to "Hello."  
   - No supervisor or agent; stream ends with `{ done: true, reply }`.

2. **Message present**  
   - **Supervisor** is called once: `supervisor_decision(api_key, provider, message)` (sync, in a thread).  
   - Returns: `run_agent` (bool), `agent` ("browser" | "desktop" | "coding" | "shell" | null), `goal`, `reasoning`, `next_steps`.

3. **If `run_agent` is false or no goal**  
   - Backend streams the **chat** reply (same LLM, no agent): `_stream_chat_reply(api_key, message, attachment_paths)` → SSE `delta` chunks, then `{ done: true, reply }`.

4. **If `run_agent` is true and goal is set**  
   - Backend builds **initial_state** (message, attachment_paths, chat_id, api_key, provider, **on_step**), starts a **drain_steps** task, and runs the **LangGraph** router with `graph.ainvoke(initial_state)`.  
   - Steps emitted by the agent are put into a queue; **drain_steps** reads the queue and calls **`_emit_agent_step`** for each payload (step, thought, action, description, result, done, optional screenshot).  
   - **`_emit_agent_step`** broadcasts that payload to all WebSocket clients on **`/ws/agent-steps`**.  
   - When the graph finishes, the stream yields one final SSE event: `{ done: true, reply }`.

So for the user: either they see **streaming chat text** or **agent steps (and screenshots) on the WebSocket**, then the **final reply** in the SSE stream.

---

## 3. Non-streaming path (POST `/chat/send-message`)

- Same **initial_state** and **LangGraph** `graph.ainvoke(initial_state)`.  
- **on_step** pushes to a queue; a **drain_steps** task runs in the background and calls **`_emit_agent_step`** so any connected WebSocket clients still see steps.  
- No SSE; the HTTP response is returned after the graph completes with `{ reply }`.

---

## 4. LangGraph router (single graph for both paths)

**State:** `RouterState` (message, attachment_paths, chat_id, api_key, provider, route, supervisor_decision, goal, reply, on_step).

**Graph shape:**

1. **Start**  
   - **Condition:** if there is no message but there are attachment_paths → go to **chat**; else go to **supervisor**.

2. **Supervisor node**  
   - Runs **supervisor_decision(api_key, provider, message)**.  
   - Writes **supervisor_decision** and **goal** into state.  
   - No `on_step` call here; the UI “Supervisor” step is emitted later by the agent nodes.

3. **After supervisor**  
   - **Condition:**  
     - If `run_agent` is false or goal is empty → **chat**.  
     - Else if agent is **"browser"** → **run_browser**.  
     - Else if agent is **"desktop"** → **run_desktop**.  
     - Else if agent is **"coding"** → **run_coding**.  
     - Else if agent is **"shell"** → **run_shell** (host terminal; requires `JARVIS_ENABLE_SHELL=1`).  
     - Else → **chat**.

4. **Chat node**  
   - Calls `client.chat(api_key, message, paths)` (current provider).  
   - Sets **reply** and **route: "chat"** in state → **END**.

5. **run_browser node**  
   - Calls **`_emit_supervisor_step(state)`** (emits step 0: reasoning, next_steps) so the UI shows the supervisor plan.  
   - Runs **run_browser_agent(goal, 10, on_step, headless=False, api_key, provider)**.  
   - Sets **reply** and **route: "run_browser"** → **END**.

6. **run_desktop node**  
   - Same as above but **run_desktop_agent(goal, 10, on_step, api_key, provider)** and **route: "run_desktop"** → **END**.

7. **run_coding node**  
   - **`_emit_supervisor_step(state)`** then **run_coding_agent(goal, on_step, api_key, provider)** (LLM writes Python → **sandbox** via `tools/python_sandbox.py`).  
   - Sets **reply**, **route: "run_coding"**, optional **tool_used** (`python_sandbox`) → **END**.

8. **run_shell node**  
   - **`_emit_supervisor_step(state)`** then **run_shell_agent(goal, on_step, api_key, provider)** (LLM proposes host shell commands → `tools/shell_runner.py`).  
   - Sets **reply**, **route: "run_shell"**, optional **tool_used** (`shell`) → **END**.  
   - **Opt-in:** `JARVIS_ENABLE_SHELL=1`; default cwd `jarvis-shell-work/` (see `backend/SHELL.md`).

So the **entire agent workflow** for a given message is: **Start → (optional) Supervisor → one of Chat / run_browser / run_desktop / run_coding / run_shell → END**. Only one of these runs per request.

---

## 5. Supervisor (one LLM call)

- **Input:** api_key, provider, user message.  
- **Model:** Same as chat for that provider (e.g. GPT-4o or Grok).  
- **System prompt:** Describes five options (chat, browser, desktop, **coding**, **shell**) and the exact JSON shape to return. **Coding** = Python sandbox; **shell** = real host terminal (mkdir, drives, git, etc.) when `JARVIS_ENABLE_SHELL=1`.  
- **Heuristic:** “execute Python / factorial / .py script” → **coding** before the LLM. When shell is enabled, phrases like “mkdir”, “powershell”, “list drives”, “git clone” → **shell** before the LLM. If the LLM returns **desktop** but the text still looks programmatic, override to **coding**; if it looks like a terminal/filesystem task, override to **shell**.  
- **Output:** `run_agent`, `agent`, `goal`, `reasoning`, `next_steps`.  
- Used only to **route**; it does not produce the final reply. The actual reply is produced by the **chat** node or one of the **browser / desktop / coding / shell** agents.

---

## 6. Browser agent (Playwright)

- **Input:** goal (e.g. “open example.com”, “search google for weather”), max_steps (e.g. 10), on_step, api_key, provider.  
- **URL resolution:** From goal text: explicit URL, or “open example.com”, or “search google for X” → built URL.  
- **Flow:**  
  1. Launch Chromium, open the URL.  
  2. **Step 1:** Emit **on_step(1, "Opened ...", "navigate", ..., screenshot)**.  
  3. **Loop (step 2..max_steps):**  
     - Run a **page summary** script in the browser (interactive elements + centerX/centerY for clicks).  
     - Call **LLM** (current provider) with goal, step, last result, page summary → get **action** (click, type, scroll, done).  
     - If **done:** emit step and break.  
     - **Loop guard:** If the same action repeats 3 times → emit “Stopped (repeated action)” and break.  
     - **Execute:** click by coordinates (from summary) or by selector; type (click + Ctrl+A + type) or fill; scroll.  
     - Emit **on_step(step, thought, action, description, result, screenshot)**.  
  4. Return a text summary of the trace (e.g. "Browser task: Opened ... Step 2: ...").  

All **on_step** calls are picked up by the router’s **drain_steps** and sent to the WebSocket as agent steps (with optional screenshots).

---

## 7. Desktop agent (screenshot + vision + pyautogui)

- **Input:** goal, max_steps (e.g. 10), on_step, api_key, provider.  
- **Flow:**  
  1. **Loop (step 1..max_steps):**  
     - **Capture screen** (mss) → image + width/height.  
     - **Vision LLM** (current provider): image + goal + step + last result + image dimensions → JSON **action** (click x,y | type | scroll | done).  
     - If **done:** emit step and break.  
     - **Loop guard:** Same as browser (repeated action 3 times → stop).  
     - **Execute:** pyautogui.click(x,y), or type, or scroll.  
     - **on_step(step, thought, action, description, result, screenshot)**.  
  2. Return a text summary of the trace.  

Again, **on_step** is the same callback; the backend sends these steps over the WebSocket.

---

## 7b. Coding agent (sandboxed Python)

- **Input:** goal (e.g. “calculate factorial of 10”, “execute a Python script that …”), `on_step`, api_key, provider.  
- **Flow:**  
  1. Emit **on_step(0, …)** with a short plan (interpret task → generate code → run in sandbox).  
  2. **LLM** outputs JSON `{"code": "..."}` using only sandbox-allowed imports (see `backend/PYTHON_SANDBOX.md`).  
  3. **run_sandboxed_python** in a child process; on failure, one **retry** with the error returned to the LLM.  
  4. Further **on_step** calls for execute/done; final reply includes stdout; **tool_used** may record `python_sandbox`.  
- **No GUI** — does not use pyautogui or desktop automation for script tasks.

---

## 7c. Shell agent (host terminal, opt-in)

- **Input:** goal (e.g. “mkdir foo”, “list drives”, “run `git status`”), `on_step`, api_key, provider.  
- **Enable:** `JARVIS_ENABLE_SHELL=1` on the server (see `backend/SHELL.md`).  
- **Flow:** Multi-turn loop: LLM outputs JSON `{"done", "command", "thought}` → **run_shell_command** (PowerShell or bash under `JARVIS_SHELL_WORKDIR`) → stdout/stderr returned to the LLM until `done` or step limit.  
- **Not a security boundary** — same risk class as SSH on that machine; blocklist only catches a few catastrophic patterns.

---

## 8. Step emission and WebSocket

- **on_step(step, thought, action, description, result, done, screenshot_base64=None)** is passed in state and called by:  
  - **Supervisor step (0):** emitted by **run_browser** / **run_desktop** / **run_coding** / **run_shell** via **`_emit_supervisor_step(state)`** (reasoning, next_steps).  
  - **Browser:** navigate (step 1) then each loop step.  
  - **Desktop:** each loop step.  
  - **Coding:** plan (0), generate/execute (1), done (2).  
  - **Shell:** plan (0), one **on_step** per command, then done.  
- Each call pushes a payload to the **step_queue**. The **drain_steps** task (running alongside the graph) calls **`_emit_agent_step(...)`**, which **broadcasts** the payload to every WebSocket client connected to **`/ws/agent-steps`**.  
- Payload includes: step, thought, action, description, result, done, and optionally **screenshot** (base64). The frontend subscribes to this WebSocket and displays steps and screenshots in the chat UI.

---

## 9. Tracing and observability

- After the graph finishes (both stream and non-stream), the backend calls **trace_log(provider, route, message, reply, success, error, duration_sec, …)**.  
- **route** is the state’s **route** set by the node that ran (chat, run_browser, run_desktop, run_coding, run_shell).  
- Traces are appended to **jarvis-observability/traces/trace.jsonl** and used later for eval generation and optimization (per-model success rates, tokens, errors).

---

## 10. Self-improving loop (evals → prompts & code)

The agent gets better over time by turning **traces** and **eval results** into concrete changes:

1. **Trace** — Every chat/agent run is logged (see §9).  
2. **Generate evals** — POST `/observability/evals/generate`: an LLM turns recent traces into multi-turn eval cases; stored in `jarvis-observability/evals/eval_cases.jsonl`.  
3. **Run evals** — POST `/observability/evals/run`: each case is run with **both** OpenAI and xAI; optional LLM judge scores replies; results in `eval_runs.jsonl`, pass@1 per model.  
4. **Optimization** — POST `/observability/optimization/run`: aggregates trace stats + eval pass rates, then calls an LLM to produce:
   - **prompt_modification_instructions** (target: supervisor | browser | desktop | chat; what to add/change and why),
   - **code_addition_suggestions** (file, suggestion, reason).  
5. **Apply** — You (or automation) edit prompts/code from those instructions; the next runs and evals reflect the improvement.

So: **traces → evals → scores → optimization → prompt/code suggestions → apply → better agents**.

---

## 11. Memory architecture (planned)

Structured memory so the model can use past chats, docs, and code without filling the whole context.

**Four stores**

- **Raw chunk store** — chunk_id, content, source_type (chat, code, doc, note), source_id, created_at, version, metadata.  
- **Vector index** (Chroma) — chunk_id, embedding, metadata filters; fast semantic retrieval.  
- **Summary store** — summary_id, chunk_id/parent_id, short summary, facts/entities/decisions.  
- **Working state store** — current task, active files, recent decisions, unresolved questions, last retrieved chunk set.

**Per-turn flow (when memory is wired in)**

- **A. Parse request** — Intent, entities, active artifact, source type.  
- **B. Load task state** — Fetch working state for this session/conversation.  
- **C. Retrieve** — Query understanding → hybrid retrieval (vector + keyword + structural) → rerank → select summaries + raw chunks.  
- **D. Assemble prompt** — System + current request + task state + retrieved summaries + selected chunks (token budget: e.g. 10% task state, 20% retrieved, 35% raw, 20% response headroom).  
- **E. Generate** — Existing flow: supervisor → chat | browser | desktop | coding → reply.  
- **F. Update memory** — Update working state; **write-back** only important turns (decisions, facts, artifacts) into raw store → chunk → summarize → embed → vector + summary stores.

Chunking: **chats** by 1–5 message windows (conversation_id, turn_range, decisions); **docs** by sections/paragraphs with overlap; **code** by file/symbol (no plain-text chunking). See README for full memory design.

---

## 12. Summary diagram

**Request/response (current)**

```
User sends message (frontend)
        ↓
POST /chat/send-message/stream  (or /chat/send-message)
        ↓
[Stream path] Empty message + attachments? → Stream chat reply → done
[Stream path] Empty message? → Stream "Hello." reply → done
        ↓
supervisor_decision(api_key, provider, message)
        ↓
run_agent false or no goal? → Stream chat reply (deltas + done) → end
        ↓
run_agent true, goal set
        ↓
Build initial_state (message, paths, chat_id, api_key, provider, on_step)
Start drain_steps task (consumes step_queue → _emit_agent_step → WebSocket)
        ↓
LangGraph: __start__ → supervisor node → conditional:
        ├─ chat node        → reply + route "chat"        → END
        ├─ run_browser node → _emit_supervisor_step + run_browser_agent → reply + route "run_browser" → END
        ├─ run_desktop node → _emit_supervisor_step + run_desktop_agent → reply + route "run_desktop" → END
        └─ run_coding node  → _emit_supervisor_step + run_coding_agent → reply + route "run_coding" → END
        ↓
trace_log(provider, route, message, reply, ...)
        ↓
Stream: yield { done: true, reply }  |  Non-stream: return { reply }
```

**Self-improving loop (evals)**

```
trace.jsonl (every run)
        ↓
POST /observability/evals/generate  →  eval_cases.jsonl (multi-turn cases from logs)
        ↓
POST /observability/evals/run  →  eval_runs.jsonl, pass@1 per model
        ↓
POST /observability/optimization/run  →  trace_stats + eval_pass + LLM
        ↓
prompt_modification_instructions + code_addition_suggestions
        ↓
Apply (human or automation)  →  better prompts/code  →  next runs improve
```

**Memory (planned) — per turn**

```
Parse request  →  Load task state  →  Retrieve (vector + keyword → rerank)
        →  Assemble prompt (task state + summaries + chunks, token budget)
        →  Generate (existing supervisor → chat | browser | desktop)
        →  Update working state  →  Write-back important turns (chunk → embed → store)
```

The **agent workflow** is: one optional supervisor call, then exactly one of **chat** / **browser agent** / **desktop agent**; steps (and screenshots) are streamed over the WebSocket; the final answer is in **reply** and in the trace log. **Evals** use traces to produce prompt/code suggestions. **Memory** (when implemented) wraps each turn with retrieval and write-back for persistence and continuity.
