# IODO RAG

Self-hosted RAG pipeline for Polish legal acts and security documents.

The stack uses:

- PostgreSQL 16 with `pgvector`
- Hugging Face Text Embeddings Inference with `intfloat/multilingual-e5-small`
- Python ingestion for text PDFs and DOCX
- FastAPI/Uvicorn web interface for browser uploads
- hybrid retrieval: vector similarity + PostgreSQL full-text search

## Start

```bash
cd /opt/IODO
cp .env.example .env
docker compose up -d postgres tei web
docker compose --profile tools build app
```

The first `tei` startup downloads `intfloat/multilingual-e5-small`, so it can take a while.

## Import documents

Put files in `data/inbox`, then run:

```bash
docker compose --profile tools run --rm app ingest /data/inbox
```

Single file:

```bash
docker compose --profile tools run --rm app ingest /data/inbox/example.pdf
```

Supported now:

- `.pdf` with extractable text
- `.docx`

Scanned PDFs need an OCR step before ingestion. Add PaddleOCR, Tesseract, or another internal OCR service before calling the importer.

## Search

```bash
docker compose --profile tools run --rm app search "jakie są obowiązki administratora danych w razie incydentu bezpieczeństwa?"
```

Limit:

```bash
docker compose --profile tools run --rm app search "kontrola dostępu do systemów teleinformatycznych" --limit 10
```

## Web Import Interface

Start the browser upload interface:

```bash
cd /opt/IODO
docker compose up -d postgres tei web
```

Open:

```text
http://192.168.1.14
http://192.168.1.14:8000
http://localhost
http://localhost:8000
```

The interface accepts one or many `.pdf` and `.docx` files, stores uploaded files under `/opt/IODO/data/uploads`, runs the same embedding pipeline as the CLI importer, and writes chunks to PostgreSQL.

Embedding requests are batched with `EMBEDDING_BATCH_SIZE=8`, which avoids TEI `422 Unprocessable Entity` errors for larger documents that produce many chunks.

The embedding path used by both web and CLI was verified with `EmbeddingClient('http://tei:80', 384).embed(50 texts)`: it returned `50` vectors with dimension `384`.

Current Compose publishing:

```text
80:8000
8000:8000
```

`192.168.1.14` is the current LAN address observed on this host. If DHCP changes it, check the active host address before connecting from another machine.

Healthchecks:

```bash
curl http://192.168.1.14/health
curl http://192.168.1.14:8000/health
curl http://localhost/health
curl http://localhost:8000/health
```

## Database

Important tables:

- `documents`: one row per source file
- `document_chunks`: text chunks with metadata, `vector(384)` embedding, and `tsvector`

The schema is initialized from `db/init.sql`.

## Production Notes

For Polish law and security documents, retrieval quality usually depends more on ingestion than on the embedding model alone:

- keep legal structure in metadata: chapter, article, paragraph, point
- preserve source file and page references
- use hybrid retrieval, not only vector search
- add a reranker after the first retrieval stage
- evaluate on 30-50 real Polish questions with known correct fragments

Recommended next additions:

- OCR pipeline for scanned PDFs
- `BAAI/bge-reranker-v2-m3` as a local reranker
- document versioning and validity dates
- authenticated API endpoint for application integration

## Documentation

- `docs/STATUS.md`: current deployment status and completed work
- `docs/OPERATIONS.md`: operational commands and troubleshooting
- `docs/NEXT_STEPS.md`: recommended next implementation steps
- `docs/WORKFLOW.md`: documentation workflow for future project changes

## Service support panel

The separate support panel runs on port `8081` and uses `support-web`, `support-worker`, Ollama, TEI and the GTE reranker. Start it with:

```bash
docker compose up -d postgres tei ollama reranker support-web support-worker
```

Current support documentation:

- `dev-docs/00-INDEX.md`: architecture and implementation documentation index;
- `dev-docs/PANEL_GUIDE.md`: operator guide for tickets, model suggestions, feedback and knowledge publication;
- `dev-docs/OPERATIONS.md`: deployment, migrations, health and backup;
- `dev-docs/SECURITY.md`: roles, sessions, CSRF and tenant/system isolation;
- `dev-docs/TESTING.md`: unit, integration and evaluation requirements;
- `dev-docs/NEXT_STEPS.md`: current execution status and upcoming pilot work.
