"""Authentication dependencies for API v2."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from fastapi import status

import app.state
from app.repositories import api_keys as api_keys_repo
from app.repositories import users as users_repo


async def get_api_key_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict | None:
    """
    Validate API key from Authorization header.
    Returns user data if valid, None if no key provided, raises HTTPException if invalid.
    """
    if not authorization:
        return None
    
    # Check if it's a Bearer token
    if not authorization.startswith("Bearer "):
        return None
    
    # Extract the API key
    api_key = authorization[7:]  # Remove "Bearer " prefix
    
    # Check if it's an API key (starts with bancho_v2_)
    if not api_key.startswith("bancho_v2_"):
        return None
    
    # Hash the key for lookup
    from app.api.v2.models.api_keys import hash_api_key
    api_key_hash = hash_api_key(api_key)
    
    # Fetch the API key from database
    key_data = await api_keys_repo.fetch_one(api_key_hash=api_key_hash)
    
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    # Check if revoked
    if key_data["revoked"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked",
        )
    
    # Check if expired
    if key_data["expires_at"] and key_data["expires_at"] < datetime.now():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )
    
    # Update last used timestamp (async, don't wait)
    app.state.loop.create_task(api_keys_repo.update_last_used(api_key_hash))
    
    # Fetch and return user data
    user_data = await users_repo.fetch_one(id=key_data["user_id"])
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    return user_data


async def require_api_key(
    user: Annotated[dict | None, Depends(get_api_key_user)],
) -> dict:
    """Require a valid API key."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user
