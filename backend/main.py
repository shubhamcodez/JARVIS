"""FastAPI backend: chat, send_message (classify + agent/chat), chat log, storage, WebSocket for agent steps."""
from __future__ import annotations

import asyncio
import queue
from typing import Optional

import json

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import get_openai_api_key
from openai_client import chat as openai_chat, chat_stream
from agents.supervisor import supervisor_decision
from chat_log import (
    append_chat_log,
    list_chats,
    set_current_chat,
    get_current_chat_id,
    read_chat_log,
)
from storage import get_chats_storage_path, set_chats_storage_path
from agents.router import create_router_graph

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


# Lazy-compiled router graph (LangGraph)
_router_graph = None


def _get_router_graph():
    global _router_graph
    if _router_graph is None:
        _router_graph = create_router_graph()
    return _router_graph


async def _emit_agent_step(
    step: int,
    thought: str,
    action: str,
    description: str,
    result: Optional[str],
    done: bool,
    screenshot: Optional[str] = None,
):
    payload = {
        "step": step,
        "thought": thought,
        "action": action,
        "description": description,
        "result": result,
        "done": done,
    }
    if screenshot is not None:
        payload["screenshot"] = screenshot
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
    Main entry: LangGraph router classifies then routes to chat, browser agent, or desktop agent.
    """
    api_key = get_openai_api_key()
    message = (body.message or "").strip()
    attachment_paths = body.attachment_paths or []
    chat_id = body.chat_id

    step_queue: queue.Queue = queue.Queue()

    def on_step(step, thought, action, description, result, done, screenshot_base64=None):
        step_queue.put({
            "step": step, "thought": thought or "", "action": action or "",
            "description": description or "", "result": result, "done": done,
            "screenshot": screenshot_base64,
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
                payload.get("screenshot"),
            )

    initial_state = {
        "message": message,
        "attachment_paths": attachment_paths,
        "chat_id": chat_id,
        "api_key": api_key,
        "on_step": on_step,
    }
    graph = _get_router_graph()
    drain_task = asyncio.create_task(drain_steps())
    try:
        result = await graph.ainvoke(initial_state)
        reply = result.get("reply") or "No response."
    finally:
        step_queue.put(_SENTINEL)
        await drain_task
    return {"reply": reply}


@app.post("/chat/send-message/stream")
async def send_message_stream(body: SendMessageRequest):
    """
    Streaming variant: classify first; if chat, stream SSE chunks; else run agent and send one final SSE event.
    """
    api_key = get_openai_api_key()
    message = (body.message or "").strip()
    attachment_paths = body.attachment_paths or []
    chat_id = body.chat_id
    has_attachments = len(attachment_paths) > 0

    async def _stream_chat_reply(api_key_, msg_, paths_):
        """Run sync chat_stream in executor and yield SSE as chunks arrive via queue."""
        chunk_queue = queue.Queue()
        loop = asyncio.get_event_loop()

        def producer():
            try:
                for c in chat_stream(api_key_, msg_, paths_):
                    chunk_queue.put(c)
            finally:
                chunk_queue.put(None)

        asyncio.create_task(loop.run_in_executor(None, producer))
        full = []
        while True:
            chunk = await loop.run_in_executor(None, chunk_queue.get)
            if chunk is None:
                break
            full.append(chunk)
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True, 'reply': ''.join(full)})}\n\n"

    async def event_stream():
        # Attachments-only: go straight to chat stream
        if not message and has_attachments:
            msg = "Please summarize or answer based on the attached documents."
            async for line in _stream_chat_reply(api_key, msg, attachment_paths):
                yield line
            return

        if not message:
            async for line in _stream_chat_reply(api_key, "Hello.", None):
                yield line
            return

        decision = await asyncio.to_thread(supervisor_decision, api_key, message)
        goal = (decision.get("goal") or message).strip()
        is_task = decision.get("run_agent") and bool(goal)

        if not is_task:
            async for line in _stream_chat_reply(api_key, message, attachment_paths or None):
                yield line
            return

        # Agent path: run graph then one event
        step_queue = queue.Queue()

        def on_step(step, thought, action, description, result, done, screenshot_base64=None):
            step_queue.put({
                "step": step, "thought": thought or "", "action": action or "",
                "description": description or "", "result": result, "done": done,
                "screenshot": screenshot_base64,
            })

        async def drain_steps():
            loop = asyncio.get_event_loop()
            while True:
                payload = await loop.run_in_executor(None, step_queue.get)
                if payload is _SENTINEL:
                    break
                await _emit_agent_step(
                    payload["step"], payload["thought"], payload["action"],
                    payload["description"], payload.get("result"), payload.get("done", False),
                    payload.get("screenshot"),
                )

        initial_state = {
            "message": message,
            "attachment_paths": attachment_paths,
            "chat_id": chat_id,
            "api_key": api_key,
            "on_step": on_step,
        }
        graph = _get_router_graph()
        drain_task = asyncio.create_task(drain_steps())
        try:
            result = await graph.ainvoke(initial_state)
            reply = result.get("reply") or "No response."
        finally:
            step_queue.put(_SENTINEL)
            await drain_task
        yield f"data: {json.dumps({'done': True, 'reply': reply})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
