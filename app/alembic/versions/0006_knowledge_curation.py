"""Client-scoped cases and model-assisted knowledge curation."""
from alembic import op

revision = "0006_knowledge_curation"
down_revision = "0005_external_llm"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE support.historical_cases
      ADD COLUMN client_id bigint REFERENCES public.clients(id),
      ADD COLUMN canonical_problem_id bigint REFERENCES support.canonical_problems(id),
      ADD COLUMN solution_id bigint REFERENCES support.solutions(id);
    CREATE INDEX historical_cases_visibility_idx
      ON support.historical_cases(program_id,client_id,status,created_at DESC);

    CREATE TABLE support.knowledge_curation_runs(
      id uuid PRIMARY KEY,
      ticket_id uuid NOT NULL REFERENCES support.tickets(id) ON DELETE CASCADE,
      actor_id bigint NOT NULL REFERENCES support.users(id),
      client_id bigint REFERENCES public.clients(id),
      scope text NOT NULL CHECK(scope IN ('global','client')),
      provider text NOT NULL,
      decision jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS support.knowledge_curation_runs;
    DROP INDEX IF EXISTS support.historical_cases_visibility_idx;
    ALTER TABLE support.historical_cases
      DROP COLUMN IF EXISTS solution_id,
      DROP COLUMN IF EXISTS canonical_problem_id,
      DROP COLUMN IF EXISTS client_id;
    """)
