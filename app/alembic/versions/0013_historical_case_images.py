"""Add screenshots to historical service cases."""
from alembic import op

revision = "0013_historical_case_images"
down_revision = "0012_ticket_images"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE support.historical_case_images(
      id uuid PRIMARY KEY,
      case_id uuid NOT NULL REFERENCES support.historical_cases ON DELETE CASCADE,
      purpose text NOT NULL CHECK(purpose IN ('problem','solution')),
      original_name text NOT NULL,
      storage_path text NOT NULL,
      mime_type text NOT NULL CHECK(mime_type IN ('image/jpeg','image/png','image/webp')),
      byte_size bigint NOT NULL CHECK(byte_size>0 AND byte_size<=10485760),
      uploaded_by bigint NOT NULL REFERENCES support.users,
      uploaded_at timestamptz NOT NULL DEFAULT now(),
      ai_approved_by bigint REFERENCES support.users,
      ai_approved_at timestamptz,
      ai_approval_note text
    );
    CREATE INDEX historical_case_images_case_idx
      ON support.historical_case_images(case_id,uploaded_at);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS support.historical_case_images;")
