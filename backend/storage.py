"""Chats storage path: get/set via config file."""
from pathlib import Path

from config import chats_config_path, chats_dir


def get_chats_storage_path() -> str:
    return str(chats_dir())


def set_chats_storage_path(path: str) -> None:
    path = (path or "").strip()
    if not path:
        raise ValueError("Path cannot be empty.")
    p = chats_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(path, encoding="utf-8")
    from memory.chat_log import clear_current_chat
    clear_current_chat()
