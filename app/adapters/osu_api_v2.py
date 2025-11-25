from __future__ import annotations

import asyncio
from typing import Any, TypedDict, Literal
from datetime import datetime, timedelta

import app.settings
import app.state
from app.logging import Ansi, log


class OAuth2Token(TypedDict):
    access_token: str
    expires_at: datetime


# Global token cache
_oauth_token: OAuth2Token | None = None


async def get_oauth_token() -> str:
    """Get or refresh OAuth2 token for osu! API v2."""
    global _oauth_token
    
    # Check if we have a valid cached token
    if _oauth_token and _oauth_token["expires_at"] > datetime.now():
        return _oauth_token["access_token"]
    
    # Request new token
    if not app.settings.OSU_CLIENT_ID or not app.settings.OSU_CLIENT_SECRET:
        raise ValueError("OSU_CLIENT_ID and OSU_CLIENT_SECRET must be configured in .env for API v2")
    
    url = "https://osu.ppy.sh/oauth/token"
    data = {
        "client_id": int(app.settings.OSU_CLIENT_ID),
        "client_secret": app.settings.OSU_CLIENT_SECRET,
        "grant_type": "client_credentials",
        "scope": "public"
    }
    
    response = await app.state.services.http_client.post(url, json=data)
    response.raise_for_status()
    token_data = response.json()
    
    # Cache the token with expiration
    _oauth_token = {
        "access_token": token_data["access_token"],
        "expires_at": datetime.now() + timedelta(seconds=token_data.get("expires_in", 86400) - 300)  # 5 min buffer
    }
    
    return _oauth_token["access_token"]


# ==================== Beatmap Functions ====================

async def api_get_ranked_beatmaps(
    cursor_string: str | None = None,
    limit: int = 50
) -> dict[str, Any]:
    """
    Fetch ranked beatmaps from osu! API v2.
    
    Args:
        cursor_string: Pagination cursor from previous request
        limit: Number of beatmaps to fetch (max 50)
    
    Returns:
        Dict with 'beatmapsets' list and 'cursor_string' for pagination
    """
    token = await get_oauth_token()
    
    url = "https://osu.ppy.sh/api/v2/beatmapsets/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    params: dict[str, Any] = {
        "s": "ranked",  # Status: ranked
        "sort": "ranked_desc",  # Sort by ranked date descending
    }
    
    if cursor_string:
        params["cursor_string"] = cursor_string
    
    response = await app.state.services.http_client.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    return response.json()


async def api_get_beatmapset(beatmapset_id: int) -> dict[str, Any] | None:
    """
    Fetch a specific beatmapset from osu! API v2.
    
    Args:
        beatmapset_id: The beatmapset ID to fetch
    
    Returns:
        Beatmapset data or None if not found
    """
    token = await get_oauth_token()
    
    url = f"https://osu.ppy.sh/api/v2/beatmapsets/{beatmapset_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = await app.state.services.http_client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


# ==================== User Functions ====================

async def api_get_user(
    user_id: int | str,
    mode: Literal["osu", "taiko", "fruits", "mania"] = "osu"
) -> dict[str, Any] | None:
    """
    Fetch user profile from osu! API v2.
    
    Args:
        user_id: User ID or username
        mode: Game mode (osu, taiko, fruits, mania)
    
    Returns:
        User data including:
        - id, username, country_code
        - avatar_url, cover_url
        - statistics (ranked_score, play_count, total_score, etc.)
        - rank_history
        - badges, medals
        - and much more
    """
    token = await get_oauth_token()
    
    url = f"https://osu.ppy.sh/api/v2/users/{user_id}/{mode}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = await app.state.services.http_client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


async def api_get_user_scores(
    user_id: int,
    score_type: Literal["best", "firsts", "recent"] = "best",
    mode: Literal["osu", "taiko", "fruits", "mania"] = "osu",
    limit: int = 100,
    offset: int = 0
) -> list[dict[str, Any]]:
    """
    Fetch user scores from osu! API v2.
    
    Args:
        user_id: User ID
        score_type: Type of scores (best, firsts, recent)
        mode: Game mode
        limit: Number of scores to fetch (max 100)
        offset: Offset for pagination
    
    Returns:
        List of score objects with full beatmap and user data
    """
    token = await get_oauth_token()
    
    url = f"https://osu.ppy.sh/api/v2/users/{user_id}/scores/{score_type}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    params = {
        "mode": mode,
        "limit": limit,
        "offset": offset
    }
    
    try:
        response = await app.state.services.http_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception:
        return []


async def api_get_user_ranking(
    mode: Literal["osu", "taiko", "fruits", "mania"] = "osu",
    ranking_type: Literal["performance", "score"] = "performance",
    country: str | None = None,
    cursor: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Fetch user rankings from osu! API v2.
    
    Args:
        mode: Game mode
        ranking_type: Ranking type (performance for pp, score for ranked score)
        country: Country code for country rankings (e.g., "US", "JP")
        cursor: Pagination cursor from previous request
    
    Returns:
        Dict with 'ranking' list and 'cursor' for pagination
        Each ranking entry includes user data and statistics
    """
    token = await get_oauth_token()
    
    url = f"https://osu.ppy.sh/api/v2/rankings/{mode}/{ranking_type}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    params: dict[str, Any] = {}
    if country:
        params["country"] = country
    if cursor:
        params["cursor"] = cursor
    
    try:
        response = await app.state.services.http_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception:
        return {"ranking": [], "cursor": None}


async def api_get_user_beatmaps(
    user_id: int,
    beatmap_type: Literal["favourite", "graveyard", "loved", "ranked", "pending"] = "ranked",
    limit: int = 50,
    offset: int = 0
) -> list[dict[str, Any]]:
    """
    Fetch beatmaps created by a user.
    
    Args:
        user_id: User ID
        beatmap_type: Type of beatmaps to fetch
        limit: Number of beatmaps (max 50)
        offset: Offset for pagination
    
    Returns:
        List of beatmapset objects
    """
    token = await get_oauth_token()
    
    url = f"https://osu.ppy.sh/api/v2/users/{user_id}/beatmapsets/{beatmap_type}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    params = {
        "limit": limit,
        "offset": offset
    }
    
    try:
        response = await app.state.services.http_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception:
        return []


async def api_download_avatar(user_id: int) -> bytes | None:
    """
    Download user's avatar image.
    
    Args:
        user_id: User ID
    
    Returns:
        Image bytes or None if failed
    """
    url = f"https://a.ppy.sh/{user_id}"
    
    try:
        response = await app.state.services.http_client.get(url)
        response.raise_for_status()
        return response.content
    except Exception:
        return None


# ==================== Score Functions ====================

async def api_get_score(
    mode: Literal["osu", "taiko", "fruits", "mania"],
    score_id: int
) -> dict[str, Any] | None:
    """
    Fetch a specific score by ID.
    
    Args:
        mode: Game mode
        score_id: Score ID
    
    Returns:
        Score data with full beatmap and user information
    """
    token = await get_oauth_token()
    
    url = f"https://osu.ppy.sh/api/v2/scores/{mode}/{score_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = await app.state.services.http_client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


async def api_get_beatmap_scores(
    beatmap_id: int,
    mode: Literal["osu", "taiko", "fruits", "mania"] = "osu",
    mods: int | None = None,
    score_type: Literal["global", "country", "friend"] = "global"
) -> list[dict[str, Any]]:
    """
    Fetch beatmap leaderboard scores from osu! API v2.
    
    Args:
        beatmap_id: Beatmap ID
        mode: Game mode
        mods: Mod combination (optional, for mod-specific leaderboards)
        score_type: Type of leaderboard (global, country, friend)
    
    Returns:
        List of scores with user data
        Each score includes: user, score, accuracy, max_combo, mods, statistics, pp, etc.
    """
    token = await get_oauth_token()
    
    url = f"https://osu.ppy.sh/api/v2/beatmaps/{beatmap_id}/scores"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    params: dict[str, Any] = {
        "mode": mode,
    }
    
    if mods is not None:
        # Convert mods to array format expected by API v2
        # API v2 expects mod acronyms like ["HD", "HR"]
        # For now, we'll use the legacy_only parameter
        params["type"] = score_type
    
    try:
        response = await app.state.services.http_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # API v2 returns scores in a 'scores' array
        return data.get("scores", [])
    except Exception:
        return []


