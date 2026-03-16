"""Embeddings for retrieval: query and chunk vectors. Uses OpenAI embeddings (required for memory)."""
from __future__ import annotations

from typing import List

from openai import OpenAI

# Same model for query and chunks for correct similarity
EMBEDDING_MODEL = "text-embedding-3-small"


def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def embed_texts(api_key: str, texts: List[str]) -> List[List[float]]:
    """
    Embed one or more texts. Uses OpenAI text-embedding-3-small.
    Returns list of embedding vectors (each is list of floats).
    """
    if not texts:
        return []
    texts = [t.strip() or " " for t in texts]
    client = _client(api_key)
    resp = client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
    # Preserve order; API returns in same order as input
    by_index = {obj.index: obj.embedding for obj in resp.data}
    return [by_index[i] for i in range(len(texts))]


def embed_single(api_key: str, text: str) -> List[float]:
    """Convenience: embed one string; returns single vector."""
    vectors = embed_texts(api_key, [text])
    return vectors[0] if vectors else []
