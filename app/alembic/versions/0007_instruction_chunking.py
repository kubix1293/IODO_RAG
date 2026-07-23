"""Use larger chunks tuned for technical instructions."""
from alembic import op

revision = "0007_instruction_chunking"
down_revision = "0006_knowledge_curation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    UPDATE support.application_settings SET value=1600,updated_at=now()
      WHERE key='chunk_target_chars';
    UPDATE support.application_settings SET value=220,updated_at=now()
      WHERE key='chunk_overlap_chars';
    """)


def downgrade():
    op.execute("""
    UPDATE support.application_settings SET value=1100,updated_at=now()
      WHERE key='chunk_target_chars';
    UPDATE support.application_settings SET value=150,updated_at=now()
      WHERE key='chunk_overlap_chars';
    """)
