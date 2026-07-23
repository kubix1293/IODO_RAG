"""Add review queue semantics and close already published reports."""
from alembic import op

revision = "0008_knowledge_review_queue"
down_revision = "0007_instruction_chunking"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    UPDATE support.tickets t
    SET status='closed',
        closed_at=COALESCE(t.closed_at,r.published_at,now()),
        updated_at=now()
    FROM support.ticket_resolution_reports r
    WHERE r.ticket_id=t.id
      AND r.published_solution_id IS NOT NULL
      AND t.status='awaiting_feedback';
    """)


def downgrade():
    pass
