"""Working state store: SQLite persistence for TaskState by session_id."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from memory.config import WORKING_STATE_DB, ensure_memory_dir
from memory.schemas import TaskState


def _get_conn() -> sqlite3.Connection:
    ensure_memory_dir()
    conn = sqlite3.connect(str(WORKING_STATE_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS task_state (
            session_id TEXT PRIMARY KEY,
            current_goal TEXT NOT NULL DEFAULT '',
            active_chunk_ids TEXT NOT NULL DEFAULT '[]',
            recent_decisions TEXT NOT NULL DEFAULT '[]',
            open_questions TEXT NOT NULL DEFAULT '[]',
            last_retrieved_ids TEXT NOT NULL DEFAULT '[]',
            updated_at REAL NOT NULL
        );
    """)
    return conn


def get_task_state(session_id: str) -> Optional[TaskState]:
    """Load task state for session or None if not found."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM task_state WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return TaskState(
            session_id=row["session_id"],
            current_goal=row["current_goal"] or "",
            active_chunk_ids=json.loads(row["active_chunk_ids"] or "[]"),
            recent_decisions=json.loads(row["recent_decisions"] or "[]"),
            open_questions=json.loads(row["open_questions"] or "[]"),
            last_retrieved_ids=json.loads(row["last_retrieved_ids"] or "[]"),
            updated_at=row["updated_at"],
        )
    finally:
        conn.close()


def update_task_state(state: TaskState) -> None:
    """Insert or replace task state for the session."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO task_state
               (session_id, current_goal, active_chunk_ids, recent_decisions, open_questions, last_retrieved_ids, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                state.session_id,
                state.current_goal,
                json.dumps(state.active_chunk_ids, ensure_ascii=False),
                json.dumps(state.recent_decisions, ensure_ascii=False),
                json.dumps(state.open_questions, ensure_ascii=False),
                json.dumps(state.last_retrieved_ids, ensure_ascii=False),
                state.updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
