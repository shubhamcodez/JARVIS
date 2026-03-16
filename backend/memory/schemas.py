"""Memory schemas: Chunk, Summary, TaskState, and source types."""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Source of a memory chunk."""
    CHAT = "chat"
    CODE = "code"
    DOC = "doc"
    NOTE = "note"
    AGENT_TRACE = "agent_trace"


class Chunk(BaseModel):
    """Raw memory chunk: content plus provenance and metadata."""
    chunk_id: str
    content: str
    source_type: SourceType
    source_id: str  # e.g. conversation_id, file path, doc id
    parent_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    version: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class Summary(BaseModel):
    """Summary of one or more chunks (Phase 2)."""
    summary_id: str
    chunk_id: Optional[str] = None
    parent_id: Optional[str] = None
    content: str
    facts: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)

    class Config:
        use_enum_values = True


class TaskState(BaseModel):
    """Working state for the current session/task."""
    session_id: str  # e.g. chat_id
    current_goal: str = ""
    active_chunk_ids: list[str] = Field(default_factory=list)
    recent_decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    last_retrieved_ids: list[str] = Field(default_factory=list)
    updated_at: float = Field(default_factory=time.time)

    class Config:
        use_enum_values = True
