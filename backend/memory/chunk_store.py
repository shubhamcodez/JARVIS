"""Raw chunk store: SQLite persistence for Chunk records."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from memory.config import CHUNKS_DB, ensure_memory_dir
from memory.schemas import Chunk, SourceType


def _get_conn() -> sqlite3.Connection:
    ensure_memory_dir()
    conn = sqlite3.connect(str(CHUNKS_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            parent_id TEXT,
            created_at REAL NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            metadata TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type, source_id);
    """)
    return conn


def insert_chunk(chunk: Chunk) -> None:
    """Insert or replace a chunk."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, content, source_type, source_id, parent_id, created_at, version, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.chunk_id,
                chunk.content,
                chunk.source_type.value if isinstance(chunk.source_type, SourceType) else chunk.source_type,
                chunk.source_id,
                chunk.parent_id,
                chunk.created_at,
                chunk.version,
                json.dumps(chunk.metadata, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_chunk(chunk_id: str) -> Optional[Chunk]:
    """Return chunk by id or None."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        if not row:
            return None
        return _row_to_chunk(row)
    finally:
        conn.close()


def _row_to_chunk(row: sqlite3.Row) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        content=row["content"],
        source_type=SourceType(row["source_type"]) if row["source_type"] else SourceType.CHAT,
        source_id=row["source_id"],
        parent_id=row["parent_id"],
        created_at=row["created_at"],
        version=row["version"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


def list_chunks_by_source(
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = 500,
) -> list[Chunk]:
    """List chunks, optionally filtered by source_type and/or source_id."""
    conn = _get_conn()
    try:
        if source_type and source_id:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE source_type = ? AND source_id = ? ORDER BY created_at DESC LIMIT ?",
                (source_type, source_id, limit),
            ).fetchall()
        elif source_type:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE source_type = ? ORDER BY created_at DESC LIMIT ?",
                (source_type, limit),
            ).fetchall()
        elif source_id:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE source_id = ? ORDER BY created_at DESC LIMIT ?",
                (source_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM chunks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_chunk(r) for r in rows]
    finally:
        conn.close()
