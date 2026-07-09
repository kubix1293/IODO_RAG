from __future__ import annotations

from iodo_rag.config import Settings
from typing import Any

from iodo_rag.db import adjacent_chunks, connect, hybrid_search
from iodo_rag.embeddings import EmbeddingClient


def search(
    query: str,
    settings: Settings,
    *,
    limit: int,
    client_id: int | None = None,
) -> list[dict[str, object]]:
    embedder = EmbeddingClient(settings.embedding_url, settings.embedding_dim)
    embedding = embedder.embed([query], is_query=True)[0]
    with connect(settings.database_url) as conn:
        return hybrid_search(conn, query=query, embedding=embedding, limit=limit, client_id=client_id)


def fetch_adjacent_chunks(
    chunk_ids: list[int],
    settings: Settings,
    *,
    client_id: int | None = None,
) -> list[dict[str, Any]]:
    with connect(settings.database_url) as conn:
        return adjacent_chunks(conn, chunk_ids=chunk_ids, client_id=client_id)
