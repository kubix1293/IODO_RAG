from __future__ import annotations

from pathlib import Path

from iodo_rag.chunking import split_into_chunks
from iodo_rag.config import Settings
from iodo_rag.db import connect, default_client_id, ensure_schema, file_sha256, replace_chunks, upsert_document
from iodo_rag.embeddings import EmbeddingClient
from iodo_rag.parsers import parse_document


def ingest_path(path: Path, settings: Settings, *, client_id: int | None = None) -> tuple[int, int]:
    text, parser_details, mime_type = parse_document(path)
    if not text:
        raise ValueError(f"No text extracted from {path}. This may be a scanned document requiring OCR.")

    chunks = split_into_chunks(
        text,
        target_chars=settings.chunk_target_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    if not chunks:
        raise ValueError(f"No chunks produced for {path}")

    embedder = EmbeddingClient(settings.embedding_url, settings.embedding_dim)
    embeddings = embedder.embed([str(chunk["text"]) for chunk in chunks])

    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        target_client_id = client_id or default_client_id(conn)
        document_id = upsert_document(
            conn,
            client_id=target_client_id,
            source_file=str(path),
            title=path.stem,
            sha256=file_sha256(path),
            mime_type=mime_type,
            metadata={"parser_details": parser_details},
        )
        replace_chunks(conn, document_id=document_id, chunks=chunks, embeddings=embeddings)
        conn.commit()

    return document_id, len(chunks)
