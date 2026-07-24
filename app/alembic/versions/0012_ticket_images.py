"""Add reviewed ticket images and solution links."""
from alembic import op

revision = "0012_ticket_images"
down_revision = "0011_document_chunk_review"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE support.ticket_images(
      id uuid PRIMARY KEY,
      ticket_id uuid NOT NULL REFERENCES support.tickets ON DELETE CASCADE,
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
    CREATE INDEX ticket_images_ticket_idx ON support.ticket_images(ticket_id,uploaded_at);

    CREATE TABLE support.solution_image_links(
      solution_id bigint NOT NULL REFERENCES support.solutions ON DELETE CASCADE,
      image_id uuid NOT NULL REFERENCES support.ticket_images ON DELETE CASCADE,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(solution_id,image_id)
    );
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS support.solution_image_links;
    DROP TABLE IF EXISTS support.ticket_images;
    """)
