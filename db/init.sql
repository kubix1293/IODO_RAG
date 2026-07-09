CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS clients (
  id bigserial PRIMARY KEY,
  name text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO clients (name)
VALUES ('Klient domyslny')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS documents (
  id bigserial PRIMARY KEY,
  client_id bigint REFERENCES clients(id),
  source_file text NOT NULL UNIQUE,
  title text,
  sha256 text NOT NULL,
  mime_type text,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id bigserial PRIMARY KEY,
  document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index int NOT NULL,
  title text,
  section text,
  article text,
  paragraph text,
  point text,
  page_from int,
  page_to int,
  chunk_text text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  embedding vector(384) NOT NULL,
  search_tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(section, '') || ' ' || coalesce(chunk_text, ''))
  ) STORED,
  UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw
ON document_chunks
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS document_chunks_search_idx
ON document_chunks
USING gin (search_tsv);

CREATE INDEX IF NOT EXISTS document_chunks_document_idx
ON document_chunks (document_id, chunk_index);

CREATE INDEX IF NOT EXISTS documents_client_idx
ON documents (client_id, created_at DESC, id DESC);
