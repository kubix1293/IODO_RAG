"""Add system-scoped historical service cases and seed ZZL/ASW."""
from alembic import op

revision = "0002_historical_cases"
down_revision = "0001_support"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO support.programs(name, description)
        VALUES
          ('ZZL', 'System ZZL'),
          ('ASW', 'System ASW')
        ON CONFLICT(name) DO UPDATE SET active=true;

        CREATE TABLE support.historical_cases (
          id uuid PRIMARY KEY,
          program_id bigint NOT NULL REFERENCES support.programs(id),
          title text NOT NULL,
          ticket_description text NOT NULL,
          resolution text NOT NULL,
          error_code text,
          version text,
          environment text,
          status text NOT NULL DEFAULT 'approved'
            CHECK(status IN ('draft','approved','retired')),
          created_by bigint NOT NULL REFERENCES support.users(id),
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX historical_cases_program_idx
          ON support.historical_cases(program_id, status, created_at DESC);
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS support.historical_cases")
