"""Add technician resolution reports and knowledge publication link."""
from alembic import op

revision = "0003_resolution_reports"
down_revision = "0002_historical_cases"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE support.ticket_resolution_reports (
          id uuid PRIMARY KEY,
          ticket_id uuid NOT NULL UNIQUE REFERENCES support.tickets(id) ON DELETE CASCADE,
          outcome text NOT NULL CHECK(outcome IN ('helped','partially_helped','not_helped')),
          suggestion_rating smallint NOT NULL CHECK(suggestion_rating BETWEEN 1 AND 5),
          actual_resolution text NOT NULL,
          comment text,
          created_by bigint NOT NULL REFERENCES support.users(id),
          published_solution_id bigint REFERENCES support.solutions(id),
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          published_at timestamptz
        );
        CREATE INDEX ticket_resolution_reports_outcome_idx
          ON support.ticket_resolution_reports(outcome, created_at DESC);
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS support.ticket_resolution_reports")
