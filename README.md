# JARVIS

Python-backed chatbot with OpenAI: chat, task classification, and desktop agent (vision + automation). React frontend.

## Stack

- **Backend**: Python 3.11+, FastAPI, OpenAI API, **LangGraph** (LLM orchestration), Playwright (browser control), optional pyautogui + mss (desktop agent)
- **Frontend**: React 18, Vite
- **No Rust/Tauri**: runs in the browser; backend can run locally or on a server

## Setup

1. **Python backend** (Poetry)

   Install [Poetry](https://python-poetry.org/docs/#installation) if needed, then:

   ```bash
   cd backend
   poetry install
   poetry run playwright install chromium
   ```

   (Playwright needs a browser binary once; `playwright install chromium` installs it.) Run the backend with `poetry run uvicorn main:app --reload --port 8000`, or use `npm run backend` from the project root (see below).

2. **Environment**

   Create a `.env` file in the project root with:

   ```
   OPENAI_API_KEY=your-key-here
   ```

3. **Frontend**

   ```bash
   cd web
   npm install
   ```

## Run

**Option A – Two terminals**

- Terminal 1: `npm run backend` (from project root) or `cd backend && poetry run uvicorn main:app --reload --port 8000` → backend at http://localhost:8000
- Terminal 2: `npm run dev` (from project root) → frontend at http://localhost:5173

**Option B – One command**

- From project root: `npm run dev:all` (runs backend + frontend; requires `npm install` once at root)

Open http://localhost:5173. The frontend proxies `/api` and `/ws` to the backend.

## Features

- **Chat**: Text and file attachments; uses OpenAI chat (with optional document handling).
- **Supervisor agent**: A main **supervisor** (LLM) decides for each message whether to run an agent and which one (chat | browser | desktop). It returns a goal, reasoning, and **next steps**; the UI shows the supervisor plan before the chosen agent runs.
- **Task vs chat**: The **LangGraph** router runs the supervisor, then routes to chat, browser agent, or desktop agent. URL/browser tasks (e.g. “open example.com”, “search google for X”) run the browser agent; other computer tasks run the desktop agent.
- **Browser agent**: Playwright opens a visible Chromium window, navigates to a URL (extracted or built from the goal), then uses the LLM to choose actions (click, type, scroll) from the page’s interactive elements until the goal is done. Steps stream over the same WebSocket as the desktop agent.
- **Desktop agent**: Screenshot → vision model → click/type/scroll (requires backend on the same machine with display; uses pyautogui + mss).
- **Chat history**: Stored as JSON in a configurable directory (default: `chats/` in project root). Change path in Settings.
- **Live agent steps**: WebSocket streams desktop agent steps to the UI.

## API

- `POST /chat/send-message` – Main entry (classify → agent or chat).
- `POST /chat/response` – Chat only.
- `POST /chat/send-message-with-files` – Multipart message + files.
- `GET /chat/list`, `POST /chat/set-current`, `GET /chat/read/{id}`, `POST /chat/append` – Chat log.
- `GET/POST /storage/chats-path` – Storage directory.
- `WS /ws/agent-steps` – Desktop agent step events.
