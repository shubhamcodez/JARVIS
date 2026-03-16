"""Memory: chat log, vector retrieval pipeline, and persistence."""
from .chat_log import (
    append_chat_log,
    clear_current_chat,
    get_current_chat_id,
    list_chats,
    read_chat_log,
    set_current_chat,
)
from .ingest import ingest_chat
from .prompt_assembly import inject_memory_into_user_message
from .retrieval import run_retrieval_pipeline
from .schemas import Chunk, SearchResult, WorkingState
from .vector_store import VectorStore

# Single in-memory store for retrieval; populate via ingest or write-back
_memory_store: VectorStore | None = None


def get_memory_store() -> VectorStore:
    """Return the global vector store for memory retrieval (lazy init)."""
    global _memory_store
    if _memory_store is None:
        _memory_store = VectorStore()
    return _memory_store


__all__ = [
    "append_chat_log",
    "Chunk",
    "clear_current_chat",
    "get_current_chat_id",
    "get_memory_store",
    "inject_memory_into_user_message",
    "ingest_chat",
    "list_chats",
    "read_chat_log",
    "run_retrieval_pipeline",
    "SearchResult",
    "set_current_chat",
    "WorkingState",
]
