"""Add persistent support consultation chats."""
from alembic import op

revision = "0009_support_consultations"
down_revision = "0008_knowledge_review_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE support.consultation_chats(
      id uuid PRIMARY KEY,
      created_by bigint NOT NULL REFERENCES support.users(id),
      ticket_id uuid REFERENCES support.tickets(id) ON DELETE SET NULL,
      program_id bigint NOT NULL REFERENCES support.programs(id),
      client_id bigint REFERENCES public.clients(id),
      title text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX consultation_chats_owner_idx
      ON support.consultation_chats(created_by,updated_at DESC);
    CREATE TABLE support.consultation_messages(
      id bigserial PRIMARY KEY,
      chat_id uuid NOT NULL REFERENCES support.consultation_chats(id) ON DELETE CASCADE,
      role text NOT NULL CHECK(role IN ('user','assistant')),
      content text NOT NULL,
      sources jsonb NOT NULL DEFAULT '[]',
      provider text,
      provider_error text,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX consultation_messages_chat_idx
      ON support.consultation_messages(chat_id,id);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS support.consultation_messages; DROP TABLE IF EXISTS support.consultation_chats;")
