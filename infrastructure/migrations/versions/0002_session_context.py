"""Durable deterministic context state per project/MCP session."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mcp_sessions", sa.Column("context_state", sa.JSON(), nullable=False, server_default="{}")
    )


def downgrade():
    op.drop_column("mcp_sessions", "context_state")
