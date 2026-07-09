from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from iodo_rag.vector import to_pgvector


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row)


def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
              id bigserial PRIMARY KEY,
              name text NOT NULL UNIQUE,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            INSERT INTO clients (name)
            VALUES ('Klient domyslny')
            ON CONFLICT (name) DO NOTHING
            """
        )
        cur.execute("SELECT id FROM clients WHERE name = 'Klient domyslny'")
        default_client_id = int(cur.fetchone()["id"])
        cur.execute(
            """
            ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS client_id bigint REFERENCES clients(id)
            """
        )
        cur.execute(
            "UPDATE documents SET client_id = %s WHERE client_id IS NULL",
            (default_client_id,),
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_client_idx
            ON documents (client_id, created_at DESC, id DESC)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS document_chunks_document_chunk_idx
            ON document_chunks (document_id, chunk_index)
            """
        )


def list_clients(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              cl.id,
              cl.name,
              cl.created_at,
              count(DISTINCT d.id) AS documents,
              count(c.id) AS chunks
            FROM clients cl
            LEFT JOIN documents d ON d.client_id = cl.id
            LEFT JOIN document_chunks c ON c.document_id = d.id
            GROUP BY cl.id
            ORDER BY cl.name
            """
        )
        return list(cur.fetchall())


def create_client(conn: psycopg.Connection, *, name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO clients (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (name,),
        )
        return int(cur.fetchone()["id"])


def get_client(conn: psycopg.Connection, *, client_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, created_at FROM clients WHERE id = %s", (client_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def default_client_id(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM clients ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if row:
            return int(row["id"])
        return create_client(conn, name="Klient domyslny")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def upsert_document(
    conn: psycopg.Connection,
    *,
    client_id: int,
    source_file: str,
    title: str | None,
    sha256: str,
    mime_type: str | None,
    metadata: dict[str, Any],
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (client_id, source_file, title, sha256, mime_type, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (source_file) DO UPDATE SET
              client_id = EXCLUDED.client_id,
              title = EXCLUDED.title,
              sha256 = EXCLUDED.sha256,
              mime_type = EXCLUDED.mime_type,
              metadata = EXCLUDED.metadata
            RETURNING id
            """,
            (client_id, source_file, title, sha256, mime_type, json.dumps(metadata)),
        )
        return int(cur.fetchone()["id"])


def replace_chunks(
    conn: psycopg.Connection,
    *,
    document_id: int,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings length mismatch")

    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))

        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            cur.execute(
                """
                INSERT INTO document_chunks (
                  document_id, chunk_index, title, section, article, paragraph, point,
                  page_from, page_to, chunk_text, metadata, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)
                """,
                (
                    document_id,
                    index,
                    chunk.get("title"),
                    chunk.get("section"),
                    chunk.get("article"),
                    chunk.get("paragraph"),
                    chunk.get("point"),
                    chunk.get("page_from"),
                    chunk.get("page_to"),
                    chunk["text"],
                    json.dumps(chunk.get("metadata", {})),
                    to_pgvector(embedding),
                ),
            )


def delete_document(conn: psycopg.Connection, *, document_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM documents
            WHERE id = %s
            RETURNING id, client_id, source_file, title
            """,
            (document_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def hybrid_search(
    conn: psycopg.Connection,
    *,
    query: str,
    embedding: list[float],
    limit: int,
    client_id: int | None = None,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH vector_results AS (
              SELECT
                c.id,
                row_number() OVER (ORDER BY c.embedding <=> %s::vector) AS vector_rank,
                c.embedding <=> %s::vector AS distance
              FROM document_chunks c
              JOIN documents d ON d.id = c.document_id
              WHERE (%s::bigint IS NULL OR d.client_id = %s::bigint)
              ORDER BY c.embedding <=> %s::vector
              LIMIT 80
            ),
            text_results AS (
              SELECT
                c.id,
                row_number() OVER (ORDER BY ts_rank_cd(c.search_tsv, plainto_tsquery('simple', %s)) DESC) AS text_rank,
                ts_rank_cd(c.search_tsv, plainto_tsquery('simple', %s)) AS text_score
              FROM document_chunks c
              JOIN documents d ON d.id = c.document_id
              WHERE (%s::bigint IS NULL OR d.client_id = %s::bigint)
                AND c.search_tsv @@ plainto_tsquery('simple', %s)
              ORDER BY text_score DESC
              LIMIT 80
            )
            SELECT
              c.id,
              c.document_id,
              c.chunk_index,
              d.client_id,
              cl.name AS client_name,
              d.source_file,
              d.title AS document_title,
              c.title,
              c.section,
              c.article,
              c.paragraph,
              c.point,
              c.page_from,
              c.page_to,
              c.chunk_text,
              c.metadata,
              coalesce(1.0 / (60 + vector_results.vector_rank), 0) +
              coalesce(1.0 / (60 + text_results.text_rank), 0) AS hybrid_score,
              vector_results.distance,
              text_results.text_score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN clients cl ON cl.id = d.client_id
            LEFT JOIN vector_results ON vector_results.id = c.id
            LEFT JOIN text_results ON text_results.id = c.id
            WHERE vector_results.id IS NOT NULL OR text_results.id IS NOT NULL
            ORDER BY hybrid_score DESC
            LIMIT %s
            """,
            (
                to_pgvector(embedding),
                to_pgvector(embedding),
                client_id,
                client_id,
                to_pgvector(embedding),
                query,
                query,
                client_id,
                client_id,
                query,
                limit,
            ),
        )
        return list(cur.fetchall())


def adjacent_chunks(
    conn: psycopg.Connection,
    *,
    chunk_ids: list[int],
    client_id: int | None = None,
) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH seeds AS (
              SELECT
                seed.id AS seed_id,
                seed.document_id,
                seed.chunk_index
              FROM document_chunks seed
              JOIN documents sd ON sd.id = seed.document_id
              WHERE seed.id = ANY(%s::bigint[])
                AND (%s::bigint IS NULL OR sd.client_id = %s::bigint)
            )
            SELECT
              c.id,
              c.document_id,
              c.chunk_index,
              d.client_id,
              cl.name AS client_name,
              d.source_file,
              d.title AS document_title,
              c.title,
              c.section,
              c.article,
              c.paragraph,
              c.point,
              c.page_from,
              c.page_to,
              c.chunk_text,
              c.metadata,
              seeds.seed_id,
              c.chunk_index - seeds.chunk_index AS neighbor_offset
            FROM seeds
            JOIN document_chunks c
              ON c.document_id = seeds.document_id
             AND c.chunk_index BETWEEN seeds.chunk_index - 1 AND seeds.chunk_index + 1
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN clients cl ON cl.id = d.client_id
            ORDER BY seeds.seed_id, c.chunk_index
            """,
            (chunk_ids, client_id, client_id),
        )
        return list(cur.fetchall())
