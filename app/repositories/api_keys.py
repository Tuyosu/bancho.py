"""Repository for API key operations."""
from __future__ import annotations

from typing import Any

import app.state


async def create(
    user_id: int,
    api_key_hash: str,
    description: str | None = None,
    scopes: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Create a new API key."""
    query = """
        INSERT INTO api_keys (user_id, api_key_hash, description, scopes, expires_at)
        VALUES (:user_id, :api_key_hash, :description, :scopes, :expires_at)
    """
    
    key_id = await app.state.services.database.execute(
        query,
        {
            "user_id": user_id,
            "api_key_hash": api_key_hash,
            "description": description,
            "scopes": scopes,
            "expires_at": expires_at,
        },
    )
    
    return await fetch_one(id=key_id)


async def fetch_one(
    id: int | None = None,
    api_key_hash: str | None = None,
) -> dict[str, Any] | None:
    """Fetch a single API key by ID or hash."""
    if id is not None:
        query = "SELECT * FROM api_keys WHERE id = :id"
        params = {"id": id}
    elif api_key_hash is not None:
        query = "SELECT * FROM api_keys WHERE api_key_hash = :api_key_hash"
        params = {"api_key_hash": api_key_hash}
    else:
        raise ValueError("Must provide either id or api_key_hash")
    
    return await app.state.services.database.fetch_one(query, params)


async def fetch_many(
    user_id: int,
    include_revoked: bool = False,
) -> list[dict[str, Any]]:
    """Fetch all API keys for a user."""
    query = "SELECT * FROM api_keys WHERE user_id = :user_id"
    
    if not include_revoked:
        query += " AND revoked = FALSE"
    
    query += " ORDER BY created_at DESC"
    
    return await app.state.services.database.fetch_all(query, {"user_id": user_id})


async def update(
    id: int,
    description: str | None = None,
    scopes: str | None = None,
) -> None:
    """Update an API key."""
    updates = []
    params: dict[str, Any] = {"id": id}
    
    if description is not None:
        updates.append("description = :description")
        params["description"] = description
    
    if scopes is not None:
        updates.append("scopes = :scopes")
        params["scopes"] = scopes
    
    if not updates:
        return
    
    query = f"UPDATE api_keys SET {', '.join(updates)} WHERE id = :id"
    await app.state.services.database.execute(query, params)


async def revoke(id: int) -> None:
    """Revoke an API key."""
    query = "UPDATE api_keys SET revoked = TRUE WHERE id = :id"
    await app.state.services.database.execute(query, {"id": id})


async def update_last_used(api_key_hash: str) -> None:
    """Update the last_used_at timestamp for an API key."""
    query = "UPDATE api_keys SET last_used_at = NOW() WHERE api_key_hash = :api_key_hash"
    await app.state.services.database.execute(query, {"api_key_hash": api_key_hash})
