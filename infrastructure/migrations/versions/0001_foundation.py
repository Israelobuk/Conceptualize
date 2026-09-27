"""Initial model-free application schema. This snapshot intentionally stays immutable."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("key_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("root", sa.Text(), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("git_info", sa.JSON(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "root"),
    )
    op.create_index("ix_repositories_project_id", "repositories", ["project_id"])
    op.create_table(
        "repository_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("repository_id", sa.String(36), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structure", sa.JSON(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("repository_id", "path"),
    )
    op.create_index("ix_repository_files_repository_id", "repository_files", ["repository_id"])
    op.create_table(
        "mcp_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("client", sa.String(200), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "session_id"),
    )
    op.create_index("ix_mcp_sessions_project_id", "mcp_sessions", ["project_id"])
    op.create_table(
        "context_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("otel_trace_id", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("client", sa.String(200), nullable=False),
        sa.Column("session_id", sa.String(200)),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("candidate_tokens", sa.Integer(), nullable=False),
        sa.Column("returned_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_context_requests_project_id", "context_requests", ["project_id"])
    op.create_index("ix_context_requests_timestamp", "context_requests", ["timestamp"])
    op.create_table(
        "context_results",
        sa.Column(
            "request_id", sa.String(36), sa.ForeignKey("context_requests.id"), primary_key=True
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    for table in (
        "context_results",
        "context_requests",
        "mcp_sessions",
        "repository_files",
        "repositories",
        "api_keys",
        "projects",
        "users",
    ):
        op.drop_table(table)
