"""FastAPI backend: chat, send_message (classify + agent/chat), chat log, storage, WebSocket for agent steps."""
from __future__ import annotations

import asyncio
import queue
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import get_openai_api_key
from openai_client import chat as openai_chat, classify_task
from chat_log import (
    append_chat_log,
    list_chats,
    set_current_chat,
    get_current_chat_id,
    read_chat_log,
)
from storage import get_chats_storage_path, set_chats_storage_path
from desktop_agent import run_desktop_agent

app = FastAPI(title="JARVIS API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:1430"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connections for desktop-agent-step broadcasts
_ws_connections: list[WebSocket] = []
_SENTINEL = object()


def _is_likely_url_task(goal: str) -> bool:
    g = goal.lower()
    return (
        "http://" in g or "https://" in g or ".com" in g or ".org" in g
        or g.startswith("open http") or g.startswith("navigate to http")
    )


async def _emit_agent_step(step: int, thought: str, action: str, description: str, result: Optional[str], done: bool):
    payload = {
        "step": step,
        "thought": thought,
        "action": action,
        "description": description,
        "result": result,
        "done": done,
    }
    for ws in _ws_connections[:]:
        try:
            await ws.send_json(payload)
        except Exception:
            if ws in _ws_connections:
                _ws_connections.remove(ws)


# --- Pydantic models ---
class SendMessageRequest(BaseModel):
    message: str = ""
    attachment_paths: Optional[list[str]] = None
    chat_id: Optional[str] = None


class ChatbotResponseRequest(BaseModel):
    message: str = ""
    attachment_paths: Optional[list[str]] = None


class AppendChatLogRequest(BaseModel):
    role: str
    content: str


class SetCurrentChatRequest(BaseModel):
    chat_id: str


class SetStoragePathRequest(BaseModel):
    path: str


# --- Chat ---
@app.post("/chat/response")
async def chatbot_response(body: ChatbotResponseRequest):
    """Chat only (no classification)."""
    api_key = get_openai_api_key()
    msg = (body.message or "").strip()
    paths = body.attachment_paths or []
    if not msg and paths:
        msg = "Please summarize or answer based on the attached documents."
    return {"reply": await asyncio.to_thread(openai_chat, api_key, msg, paths if paths else None)}


@app.post("/chat/send-message")
async def send_message(body: SendMessageRequest):
    """
    Main entry: classify as task or chat. If task: URL -> browser agent (stub for now),
    else desktop agent or chat.
    """
    api_key = get_openai_api_key()
    message = (body.message or "").strip()
    attachment_paths = body.attachment_paths or []
    chat_id = body.chat_id
    has_attachments = len(attachment_paths) > 0

    if not message and has_attachments:
        reply = await asyncio.to_thread(
            openai_chat, api_key, "Please summarize or answer based on the attached documents.", attachment_paths
        )
        return {"reply": reply}

    if message:
        classification = await asyncio.to_thread(classify_task, api_key, message)
        if classification.get("is_task"):
            goal = (classification.get("goal") or message).strip()
            if goal:
                if _is_likely_url_task(goal):
                    # Browser agent: placeholder (could add Playwright later)
                    reply = f"I would run the browser task (goal: {goal}). Browser automation is available when running the full agent stack."
                    return {"reply": reply}
                # Desktop agent: run in thread, steps pushed to queue; async task drains and emits via WebSocket
                step_queue: queue.Queue = queue.Queue()

                def on_step(step, thought, action, description, result, done):
                    step_queue.put({
                        "step": step, "thought": thought or "", "action": action or "",
                        "description": description or "", "result": result, "done": done,
                    })

                async def drain_steps():
                    loop = asyncio.get_event_loop()
                    while True:
                        try:
                            payload = await loop.run_in_executor(None, step_queue.get)
                        except Exception:
                            break
                        if payload is _SENTINEL:
                            break
                        await _emit_agent_step(
                            payload["step"], payload["thought"], payload["action"],
                            payload["description"], payload.get("result"), payload.get("done", False),
                        )

                drain_task = asyncio.create_task(drain_steps())
                try:
                    reply = await asyncio.to_thread(run_desktop_agent, goal, 10, on_step)
                finally:
                    step_queue.put(_SENTINEL)
                    await drain_task
                return {"reply": reply}

    reply = await asyncio.to_thread(openai_chat, api_key, message or "Hello.", attachment_paths or None)
    return {"reply": reply}


# --- Chat log ---
@app.post("/chat/append")
async def api_append_chat_log(body: AppendChatLogRequest):
    append_chat_log(body.role, body.content)
    return {}

@app.get("/chat/list")
async def api_list_chats():
    return list_chats()


@app.post("/chat/set-current")
async def api_set_current_chat(body: SetCurrentChatRequest):
    set_current_chat(body.chat_id)
    return {}


@app.get("/chat/current-id")
async def api_get_current_chat_id():
    return {"chat_id": get_current_chat_id()}


@app.get("/chat/read/{chat_id}")
async def api_read_chat_log(chat_id: str):
    return read_chat_log(chat_id)


# --- Storage ---
@app.get("/storage/chats-path")
async def api_get_chats_storage_path():
    return {"path": get_chats_storage_path()}


@app.post("/storage/chats-path")
async def api_set_chats_storage_path(body: SetStoragePathRequest):
    set_chats_storage_path(body.path)
    return {}


# --- File upload for attachments (web: frontend sends files as multipart) ---
@app.post("/chat/send-message-with-files")
async def send_message_with_files(
    message: str = Form(""),
    chat_id: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
):
    """Accept multipart form: message + files. Saves files to temp and calls send_message."""
    import tempfile
    import os
    paths = []
    try:
        for f in files:
            if not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1] or ".bin"
            fd, path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            with open(path, "wb") as out:
                out.write(await f.read())
            paths.append(path)
        body = SendMessageRequest(message=message.strip(), attachment_paths=paths if paths else None, chat_id=chat_id)
        result = await send_message(body)
        return result
    finally:
        for p in paths:
            try:
                os.unlink(p)
            except Exception:
                pass


# --- WebSocket for desktop-agent-step ---
@app.websocket("/ws/agent-steps")
async def websocket_agent_steps(ws: WebSocket):
    await ws.accept()
    _ws_connections.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ws_connections:
            _ws_connections.remove(ws)


@app.get("/health")
async def health():
    return {"status": "ok"}
