"""Administrative application settings."""
from alembic import op

revision = "0004_application_settings"
down_revision = "0003_resolution_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE support.application_settings(
      key text PRIMARY KEY,
      value integer NOT NULL,
      updated_by bigint REFERENCES support.users,
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    INSERT INTO support.application_settings(key,value) VALUES
      ('llm_timeout_seconds',1800),
      ('llm_response_tokens',500),
      ('retrieval_candidates',20),
      ('retrieval_top_sources',8),
      ('chunk_target_chars',1100),
      ('chunk_overlap_chars',150);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS support.application_settings")
