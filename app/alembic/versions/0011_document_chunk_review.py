"""Add AI-assisted document chunk review."""
from alembic import op

revision = "0011_document_chunk_review"
down_revision = "0010_longer_plain_responses"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE support.knowledge_documents
      ADD COLUMN status text NOT NULL DEFAULT 'indexed'
        CHECK(status IN ('pending_analysis','analyzing','pending_review','indexed','analysis_failed')),
      ADD COLUMN analysis_provider text,
      ADD COLUMN analysis_error text,
      ADD COLUMN document_map jsonb NOT NULL DEFAULT '{}',
      ADD COLUMN reviewed_by bigint REFERENCES support.users,
      ADD COLUMN reviewed_at timestamptz;

    CREATE TABLE support.knowledge_chunk_proposals(
      id bigserial PRIMARY KEY,
      document_id bigint NOT NULL REFERENCES support.knowledge_documents ON DELETE CASCADE,
      proposed_index int NOT NULL,
      chunk_text text NOT NULL,
      metadata jsonb NOT NULL DEFAULT '{}',
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(document_id,proposed_index)
    );
    CREATE INDEX knowledge_chunk_proposals_document_idx
      ON support.knowledge_chunk_proposals(document_id,proposed_index);
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS support.knowledge_chunk_proposals;
    ALTER TABLE support.knowledge_documents
      DROP COLUMN IF EXISTS reviewed_at,
      DROP COLUMN IF EXISTS reviewed_by,
      DROP COLUMN IF EXISTS document_map,
      DROP COLUMN IF EXISTS analysis_error,
      DROP COLUMN IF EXISTS analysis_provider,
      DROP COLUMN IF EXISTS status;
    """)
