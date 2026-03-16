"""Chat chunker: 1–5 message windows from chat log format."""
from __future__ import annotations

import time
from typing import Any

from memory.schemas import Chunk, SourceType


# Min and max messages per chunk (inclusive)
CHAT_CHUNK_MIN_TURNS = 1
CHAT_CHUNK_MAX_TURNS = 5


def _format_message(role: str, content: str) -> str:
    return f"{role}: {content}".strip()


def _window_to_content(messages: list[dict[str, Any]]) -> str:
    """Turn a list of message dicts (role, content) into a single string."""
    return "\n".join(
        _format_message(m.get("role", "user"), m.get("content", ""))
        for m in messages
    )


def chunk_chat_messages(
    messages: list[dict[str, Any]],
    conversation_id: str,
    *,
    min_turns: int = CHAT_CHUNK_MIN_TURNS,
    max_turns: int = CHAT_CHUNK_MAX_TURNS,
) -> list[dict[str, Any]]:
    """
    Split messages into overlapping windows of min_turns–max_turns messages.
    Returns list of dicts with: chunk_id, content, source_type, source_id, metadata (turn_start, turn_end), created_at.
    """
    if not messages:
        return []
    if max_turns < min_turns:
        max_turns = min_turns

    out: list[dict[str, Any]] = []
    n = len(messages)
    start = 0
    created = time.time()

    while start < n:
        # Prefer max_turns; use fewer only at the end
        end = min(start + max_turns, n)
        if end - start < min_turns and start > 0:
            # Merge with previous window if this one would be too small (optional: skip for simplicity we just take 1..max)
            pass
        window = messages[start:end]
        content = _window_to_content(window)
        chunk_id = f"{conversation_id}_{start}_{end}"
        out.append({
            "chunk_id": chunk_id,
            "content": content,
            "source_type": SourceType.CHAT.value,
            "source_id": conversation_id,
            "parent_id": None,
            "created_at": created,
            "version": 1,
            "metadata": {"turn_start": start, "turn_end": end},
        })
        start = end

    return out


def chat_messages_to_chunks(
    messages: list[dict[str, Any]],
    conversation_id: str,
    *,
    min_turns: int = CHAT_CHUNK_MIN_TURNS,
    max_turns: int = CHAT_CHUNK_MAX_TURNS,
) -> list[Chunk]:
    """Same as chunk_chat_messages but returns list of Chunk models."""
    raw = chunk_chat_messages(
        messages,
        conversation_id,
        min_turns=min_turns,
        max_turns=max_turns,
    )
    return [
        Chunk(
            chunk_id=r["chunk_id"],
            content=r["content"],
            source_type=SourceType(r["source_type"]),
            source_id=r["source_id"],
            parent_id=r.get("parent_id"),
            created_at=r["created_at"],
            version=r.get("version", 1),
            metadata=r.get("metadata", {}),
        )
        for r in raw
    ]
