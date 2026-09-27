from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(12))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("project_id", "root"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    root: Mapped[str] = mapped_column(Text)
    state_hash: Mapped[str] = mapped_column(String(64), default="")
    git_info: Mapped[dict] = mapped_column(JSON, default=dict)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RepositoryFile(Base):
    __tablename__ = "repository_files"
    __table_args__ = (UniqueConstraint("repository_id", "path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    path: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    structure: Mapped[dict] = mapped_column(JSON)
    token_count: Mapped[int] = mapped_column(Integer)


class McpSession(Base):
    __tablename__ = "mcp_sessions"
    __table_args__ = (UniqueConstraint("project_id", "session_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(200))
    client: Mapped[str] = mapped_column(String(200))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    context_state: Mapped[dict] = mapped_column(JSON, default=dict)


class ContextRequest(Base):
    __tablename__ = "context_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    otel_trace_id: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(30))
    inputs: Mapped[dict] = mapped_column(JSON)
    client: Mapped[str] = mapped_column(String(200), default="api")
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    token_budget: Mapped[int] = mapped_column(Integer)
    candidate_tokens: Mapped[int] = mapped_column(Integer, default=0)
    returned_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="success")
    revision: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class ContextResult(Base):
    __tablename__ = "context_results"
    request_id: Mapped[str] = mapped_column(ForeignKey("context_requests.id"), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
