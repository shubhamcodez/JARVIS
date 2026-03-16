"""Ingestion: turn chat (or other sources) into chunks and write to raw store (+ vector in Step 4)."""
from __future__ import annotations

from memory.chunker import chat_messages_to_chunks
from memory.chunk_store import insert_chunk
from memory.schemas import SourceType


def ingest_chat_to_chunk_store(conversation_id: str, messages: list[dict]) -> list[str]:
    """
    Chunk conversation messages and persist to raw chunk store only.
    Returns list of chunk_ids that were stored.
    """
    chunks = chat_messages_to_chunks(messages, conversation_id)
    for c in chunks:
        insert_chunk(c)
    return [c.chunk_id for c in chunks]
