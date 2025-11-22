"""API key models and utilities."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from pydantic import BaseModel


class APIKey(BaseModel):
    """API key model."""
    id: int
    user_id: int
    description: str | None
    scopes: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked: bool


class APIKeyCreate(BaseModel):
    """API key creation request."""
    description: str | None = None
    scopes: list[str] | None = None
    expires_in_days: int | None = None


class APIKeyResponse(BaseModel):
    """API key creation response (includes plain key)."""
    id: int
    api_key: str  # Only shown once
    description: str | None
    created_at: datetime
    expires_at: datetime | None


def generate_api_key() -> str:
    """Generate a secure API key."""
    # Format: bancho_v2_ + 48 random characters
    random_part = secrets.token_urlsafe(36)  # ~48 chars in base64
    return f"bancho_v2_{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash."""
    return hash_api_key(plain_key) == hashed_key
