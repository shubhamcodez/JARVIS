"""
Retrieval pipeline: current conversation → build query → vector search → rerank/filter → inject into prompt.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .embeddings import embed_single
from .query import build_retrieval_query
from .schemas import SearchResult, WorkingState
from .vector_store import VectorStore


def retrieve(
    store: VectorStore,
    openai_api_key: str,
    query_text: str,
    top_k: int = 10,
    min_score: Optional[float] = 0.2,
    source_types: Optional[List[str]] = None,
) -> List[SearchResult]:
    """
    Embed the query, run vector search, return ranked results.
    Uses OpenAI for embedding (openai_api_key required).
    """
    if not query_text.strip():
        return []
    query_embedding = embed_single(openai_api_key, query_text)
    return store.search(
        query_embedding,
        top_k=top_k,
        min_score=min_score,
        source_types=source_types,
    )


def format_retrieved_for_prompt(
    results: List[SearchResult],
    include_raw_top_n: int = 3,
    max_raw_chars: int = 2000,
) -> str:
    """
    Build the string to inject into the model context:
    - Summaries for all top results (brief)
    - Raw content only for the top include_raw_top_n (truncated by max_raw_chars).
    """
    if not results:
        return ""

    lines: List[str] = ["Relevant context from past conversations and stored memory:"]
    for i, r in enumerate(results):
        summary = (r.summary or r.raw_content or "").strip()
        if summary and i < include_raw_top_n and r.raw_content:
            content = (r.raw_content or "")[:max_raw_chars]
            if len((r.raw_content or "")) > max_raw_chars:
                content += "..."
            lines.append(f"- [{r.chunk_id}] (score {r.score}) {summary}")
            lines.append(f"  Content: {content}")
        elif summary:
            lines.append(f"- [{r.chunk_id}] (score {r.score}) {summary}")
    return "\n".join(lines)


def run_retrieval_pipeline(
    store: VectorStore,
    openai_api_key: str,
    current_message: str,
    recent_turns: Optional[List[Dict[str, str]]] = None,
    task_state: Optional[Dict[str, Any]] = None,
    working_state: Optional[WorkingState] = None,
    active_file: Optional[str] = None,
    topic_or_entities: Optional[List[str]] = None,
    top_k: int = 10,
    include_raw_top_n: int = 3,
    min_score: Optional[float] = 0.2,
) -> tuple[str, List[SearchResult]]:
    """
    Full pipeline: build query from context → vector search → format for prompt.
    Returns (context_string_to_inject, list_of_search_results).
    """
    query_text = build_retrieval_query(
        current_message=current_message,
        recent_turns=recent_turns,
        task_state=task_state,
        active_file=active_file,
        topic_or_entities=topic_or_entities,
    )
    results = retrieve(
        store=store,
        openai_api_key=openai_api_key,
        query_text=query_text,
        top_k=top_k,
        min_score=min_score,
    )
    context_str = format_retrieved_for_prompt(results, include_raw_top_n=include_raw_top_n)
    return context_str, results
