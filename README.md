# JARVIS

Python-backed chatbot with OpenAI: chat, task classification, and desktop agent (vision + automation). React frontend.

## Stack

- **Backend**: Python 3.11+, FastAPI, OpenAI API, optional pyautogui + mss for desktop agent
- **Frontend**: React 18, Vite
- **No Rust/Tauri**: runs in the browser; backend can run locally or on a server

## Setup

1. **Python backend** (Poetry)

   Install [Poetry](https://python-poetry.org/docs/#installation) if needed, then:

   ```bash
   cd backend
   poetry install
   ```

   Run the backend with `poetry run uvicorn main:app --reload --port 8000`, or use `npm run backend` from the project root (see below).

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
- **Task vs chat**: Messages are classified; computer tasks (e.g. “open Chrome”) run the desktop agent.
- **Desktop agent**: Screenshot → vision model → click/type/scroll (requires backend running on the same machine with display; uses pyautogui + mss).
- **Chat history**: Stored as JSON in a configurable directory (default: `chats/` in project root). Change path in Settings.
- **Live agent steps**: WebSocket streams desktop agent steps to the UI.

## API

- `POST /chat/send-message` – Main entry (classify → agent or chat).
- `POST /chat/response` – Chat only.
- `POST /chat/send-message-with-files` – Multipart message + files.
- `GET /chat/list`, `POST /chat/set-current`, `GET /chat/read/{id}`, `POST /chat/append` – Chat log.
- `GET/POST /storage/chats-path` – Storage directory.
- `WS /ws/agent-steps` – Desktop agent step events.
