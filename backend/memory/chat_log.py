"""Chat log: file-based persistence, same JSON format as Rust (id, title, messages, agent_session_ids)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from config import chats_dir

CHAT_EXT = "json"
CHAT_TITLE_MAX_LEN = 48

# In-memory current chat path (per process)
_current_path: Optional[Path] = None


def _chat_path(chat_id: str) -> Path:
    return chats_dir() / f"{chat_id}.{CHAT_EXT}"


def _title_from_messages(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "user":
            t = (m.get("content") or "").strip()
            if not t:
                return "New chat"
            return t[:CHAT_TITLE_MAX_LEN] + ("…" if len(t) > CHAT_TITLE_MAX_LEN else "")
    return "New chat"


def _load(path: Path) -> dict:
    if not path.exists():
        return {"id": path.stem, "title": "", "messages": [], "agent_session_ids": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("title") and data.get("messages"):
        data["title"] = _title_from_messages(data["messages"])
    return data


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_chat_log(role: str, content: str) -> None:
    global _current_path
    if role not in ("user", "assistant", "tool"):
        raise ValueError("role must be 'user', 'assistant', or 'tool'")
    root = chats_dir()
    root.mkdir(parents=True, exist_ok=True)
    if _current_path is None:
        _current_path = root / f"{int(time.time())}.{CHAT_EXT}"
    data = _load(_current_path)
    data.setdefault("messages", []).append({"role": role, "content": (content or "").strip()})
    if not data.get("title") and role == "user":
        data["title"] = _title_from_messages(data["messages"])
    _save(_current_path, data)


def list_chats() -> list[dict]:
    root = chats_dir()
    if not root.is_dir():
        return []
    entries = []
    for p in root.glob(f"*.{CHAT_EXT}"):
        try:
            data = _load(p)
            title = data.get("title") or _title_from_messages(data.get("messages", []))
            entries.append({"id": p.stem, "title": title or "New chat"})
        except Exception:
            entries.append({"id": p.stem, "title": "New chat"})
    entries.sort(key=lambda e: e["id"], reverse=True)
    return entries


def set_current_chat(chat_id: str) -> None:
    global _current_path
    _current_path = _chat_path(chat_id)


def get_current_chat_id() -> Optional[str]:
    if _current_path is None:
        return None
    return _current_path.stem


def create_new_chat() -> str:
    """Create an empty chat file, set it as current, return its id."""
    global _current_path
    root = chats_dir()
    root.mkdir(parents=True, exist_ok=True)
    chat_id = str(int(time.time()))
    path = root / f"{chat_id}.{CHAT_EXT}"
    data = {"id": chat_id, "title": "New chat", "messages": [], "agent_session_ids": []}
    _save(path, data)
    _current_path = path
    return chat_id


def delete_chat(chat_id: str) -> bool:
    """Delete a chat by id. If it was the current chat, clear current. Returns True if deleted."""
    global _current_path
    path = _chat_path(chat_id)
    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    if _current_path is not None and _current_path.resolve() == path.resolve():
        _current_path = None
    return True


def clear_current_chat() -> None:
    """Clear current chat (e.g. after storage path change)."""
    global _current_path
    _current_path = None


def read_chat_log(chat_id: str) -> list[dict]:
    path = _chat_path(chat_id)
    if not path.exists():
        return []
    data = _load(path)
    return [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in data.get("messages", [])]
