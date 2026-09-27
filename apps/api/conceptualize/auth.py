import hashlib
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from .db import get_db
from .models import ApiKey, Project

bearer = HTTPBearer(auto_error=False)


def hash_key(raw: str) -> str:
    # Random 256-bit keys are high-entropy credentials; SHA-256 is suitable for lookup.
    return hashlib.sha256(raw.encode()).hexdigest()


def create_key(db, project_id: str) -> str:
    raw = "cx_" + secrets.token_urlsafe(32)
    db.add(ApiKey(project_id=project_id, key_hash=hash_key(raw), prefix=raw[:10]))
    return raw


def authenticate(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(get_db)
) -> Project:
    if not credentials or not credentials.credentials.startswith("cx_"):
        raise HTTPException(401, "A Conceptualize API key is required")
    key = db.scalar(
        select(ApiKey).where(
            ApiKey.key_hash == hash_key(credentials.credentials), ApiKey.revoked.is_(False)
        )
    )
    if not key:
        raise HTTPException(401, "Invalid or revoked API key")
    project = db.get(Project, key.project_id)
    if not project:
        raise HTTPException(401, "Project unavailable")
    return project
