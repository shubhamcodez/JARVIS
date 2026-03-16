"""
Ingest chat history into the vector store: chunk conversations and embed.
Call after chat log updates to keep retrieval in sync with available history.
"""
from __future__ import annotations

from .chat_log import read_chat_log
from .embeddings import embed_texts
from .schemas import Chunk
from .vector_store import VectorStore

# Messages per chunk (conversation window)
CHAT_WINDOW_SIZE = 4


def _chunk_messages(chat_id: str, messages: list[dict]) -> list[Chunk]:
    """Split messages into overlapping or contiguous windows; return Chunk objects."""
    chunks: list[Chunk] = []
    for i in range(0, len(messages), CHAT_WINDOW_SIZE):
        window = messages[i : i + CHAT_WINDOW_SIZE]
        if not window:
            continue
        parts = []
        for m in window:
            role = (m.get("role") or "user").strip()
            content = (m.get("content") or "").strip()
            if content:
                parts.append(f"{role}: {content}")
        content = "\n".join(parts)
        if not content.strip():
            continue
        chunk_id = f"{chat_id}:{i}:{i + len(window)}"
        summary = content[:200] + ("..." if len(content) > 200 else "")
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                content=content,
                source_type="chat",
                source_id=chat_id,
                summary=summary,
                metadata={"turn_start": i, "turn_end": i + len(window)},
            )
        )
    return chunks


def ingest_chat(store: VectorStore, openai_api_key: str, chat_id: str) -> int:
    """
    Read chat log for chat_id, chunk into windows, embed, add to store.
    Returns number of chunks added. Does not deduplicate; call with a fresh store
    or implement upsert by chunk_id if you need idempotent ingest.
    """
    messages = read_chat_log(chat_id)
    if not messages:
        return 0
    chunks = _chunk_messages(chat_id, messages)
    if not chunks:
        return 0
    texts = [c.content for c in chunks]
    embeddings = embed_texts(openai_api_key, texts)
    for c, emb in zip(chunks, embeddings):
        store.add(c, emb)
    return len(chunks)
