"""Enable external-first hybrid LLM routing."""
from alembic import op

revision = "0005_external_llm"
down_revision = "0004_application_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    INSERT INTO support.application_settings(key,value)
    VALUES ('external_llm_enabled',1)
    ON CONFLICT(key) DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM support.application_settings WHERE key='external_llm_enabled'")
