"""Increase the configured response budget."""
from alembic import op

revision = "0010_longer_plain_responses"
down_revision = "0009_support_consultations"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    UPDATE support.application_settings
    SET value=1200,updated_at=now()
    WHERE key='llm_response_tokens' AND value<1200;
    INSERT INTO support.application_settings(key,value)
    VALUES('llm_response_tokens',1200)
    ON CONFLICT(key) DO NOTHING;
    """)


def downgrade():
    op.execute("UPDATE support.application_settings SET value=500,updated_at=now() WHERE key='llm_response_tokens' AND value=1200;")
