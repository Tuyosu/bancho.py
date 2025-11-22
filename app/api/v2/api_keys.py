"""API key management endpoints."""
from __future__ import annotations

import json
from datetime import datetime
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from app.api.v2 import responses
from app.api.v2.auth import require_api_key
from app.api.v2.common.responses import Failure
from app.api.v2.common.responses import Success
from app.api.v2.models.api_keys import APIKey
from app.api.v2.models.api_keys import APIKeyCreate
from app.api.v2.models.api_keys import APIKeyResponse
from app.api.v2.models.api_keys import generate_api_key
from app.api.v2.models.api_keys import hash_api_key
from app.repositories import api_keys as api_keys_repo

router = APIRouter()


@router.post("/api_keys")
async def create_api_key(
    data: APIKeyCreate,
    user: Annotated[dict, Depends(require_api_key)],
) -> Success[APIKeyResponse] | Failure:
    """Create a new API key for the authenticated user."""
    
    # Generate new API key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)
    
    # Calculate expiration date if specified
    expires_at = None
    if data.expires_in_days:
        expires_at = (datetime.now() + timedelta(days=data.expires_in_days)).isoformat()
    
    # Convert scopes to JSON
    scopes_json = json.dumps(data.scopes) if data.scopes else None
    
    # Create in database
    key_data = await api_keys_repo.create(
        user_id=user["id"],
        api_key_hash=api_key_hash,
        description=data.description,
        scopes=scopes_json,
        expires_at=expires_at,
    )
    
    # Return response with plain API key (only time it's shown)
    response = APIKeyResponse(
        id=key_data["id"],
        api_key=api_key,
        description=key_data["description"],
        created_at=key_data["created_at"],
        expires_at=key_data["expires_at"],
    )
    
    return responses.success(response)


@router.get("/api_keys")
async def list_api_keys(
    user: Annotated[dict, Depends(require_api_key)],
    include_revoked: bool = False,
) -> Success[list[APIKey]] | Failure:
    """List all API keys for the authenticated user."""
    
    keys = await api_keys_repo.fetch_many(
        user_id=user["id"],
        include_revoked=include_revoked,
    )
    
    response = [APIKey.from_mapping(key) for key in keys]
    return responses.success(response)


@router.patch("/api_keys/{key_id}")
async def update_api_key(
    key_id: int,
    description: str | None = None,
    scopes: list[str] | None = None,
    user: Annotated[dict, Depends(require_api_key)] = None,
) -> Success[APIKey] | Failure:
    """Update an API key's description or scopes."""
    
    # Fetch the key to verify ownership
    key_data = await api_keys_repo.fetch_one(id=key_id)
    
    if not key_data:
        return responses.failure(
            message="API key not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    
    if key_data["user_id"] != user["id"]:
        return responses.failure(
            message="Unauthorized",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    
    # Convert scopes to JSON if provided
    scopes_json = json.dumps(scopes) if scopes is not None else None
    
    # Update the key
    await api_keys_repo.update(
        id=key_id,
        description=description,
        scopes=scopes_json,
    )
    
    # Fetch updated key
    updated_key = await api_keys_repo.fetch_one(id=key_id)
    response = APIKey.from_mapping(updated_key)
    
    return responses.success(response)


@router.delete("/api_keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user: Annotated[dict, Depends(require_api_key)],
) -> Success[dict] | Failure:
    """Revoke an API key."""
    
    # Fetch the key to verify ownership
    key_data = await api_keys_repo.fetch_one(id=key_id)
    
    if not key_data:
        return responses.failure(
            message="API key not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    
    if key_data["user_id"] != user["id"]:
        return responses.failure(
            message="Unauthorized",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    
    # Revoke the key
    await api_keys_repo.revoke(key_id)
    
    return responses.success({"message": "API key revoked successfully"})
