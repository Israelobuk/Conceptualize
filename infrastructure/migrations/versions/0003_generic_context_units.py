"""Persist source-agnostic context units."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "context_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("unit_id", sa.String(1000), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(1000), nullable=False),
        sa.Column("parent_id", sa.String(1000)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.String(100), nullable=False, server_default="1"),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(100), nullable=False),
        sa.Column("updated_at", sa.String(100), nullable=False),
        sa.Column("relationships", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "unit_id"),
    )
    op.create_index("ix_context_units_project_id", "context_units", ["project_id"])
    op.create_index("ix_context_units_source_type", "context_units", ["source_type"])


def downgrade():
    op.drop_index("ix_context_units_source_type", table_name="context_units")
    op.drop_index("ix_context_units_project_id", table_name="context_units")
    op.drop_table("context_units")
