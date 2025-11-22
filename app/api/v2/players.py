"""bancho.py's v2 apis for interacting with players"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import status
from fastapi.param_functions import Query

import app.state
import app.state.sessions
from app.api.v2.common import responses
from app.api.v2.common.responses import Failure
from app.api.v2.common.responses import Success
from app.api.v2.models.players import Player
from app.api.v2.models.players import PlayerStats
from app.api.v2.models.players import PlayerStatus
from app.repositories import stats as stats_repo
from app.repositories import users as users_repo

router = APIRouter()


@router.get("/players")
async def get_players(
    priv: int | None = None,
    country: str | None = None,
    clan_id: int | None = None,
    clan_priv: int | None = None,
    preferred_mode: int | None = None,
    play_style: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> Success[list[Player]] | Failure:
    players = await users_repo.fetch_many(
        priv=priv,
        country=country,
        clan_id=clan_id,
        clan_priv=clan_priv,
        preferred_mode=preferred_mode,
        play_style=play_style,
        page=page,
        page_size=page_size,
    )
    total_players = await users_repo.fetch_count(
        priv=priv,
        country=country,
        clan_id=clan_id,
        clan_priv=clan_priv,
        preferred_mode=preferred_mode,
        play_style=play_style,
    )

    response = [Player.from_mapping(rec) for rec in players]

    return responses.success(
        content=response,
        meta={
            "total": total_players,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/players/{player_id}")
async def get_player(player_id: int) -> Success[Player] | Failure:
    data = await users_repo.fetch_one(id=player_id)
    if data is None:
        return responses.failure(
            message="Player not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    response = Player.from_mapping(data)
    return responses.success(response)


@router.get("/players/{player_id}/status")
async def get_player_status(player_id: int) -> Success[PlayerStatus] | Failure:
    player = app.state.sessions.players.get(id=player_id)

    if not player:
        return responses.failure(
            message="Player status not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    response = PlayerStatus(
        login_time=int(player.login_time),
        action=int(player.status.action),
        info_text=player.status.info_text,
        mode=int(player.status.mode),
        mods=int(player.status.mods),
        beatmap_id=player.status.map_id,
    )
    return responses.success(response)


@router.get("/players/{player_id}/stats/{mode}")
async def get_player_mode_stats(
    player_id: int,
    mode: int,
) -> Success[PlayerStats] | Failure:
    data = await stats_repo.fetch_one(player_id, mode)
    if data is None:
        return responses.failure(
            message="Player stats not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    response = PlayerStats.from_mapping(data)
    return responses.success(response)


@router.get("/players/{player_id}/stats")
async def get_player_stats(
    player_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> Success[list[PlayerStats]] | Failure:
    data = await stats_repo.fetch_many(
        player_id=player_id,
        page=page,
        page_size=page_size,
    )
    total_stats = await stats_repo.fetch_count(
        player_id=player_id,
    )

    response = [PlayerStats.from_mapping(rec) for rec in data]
    return responses.success(
        response,
        meta={
            "total": total_stats,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/players/{player_id}/recent")
async def get_player_recent_scores(
    player_id: int,
    mode: int | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> Success[list[dict]] | Failure:
    """Get player's recent scores (last 50 by default)."""
    from app.api.v2.models.scores import Score
    from app.repositories import scores as scores_repo
    
    # Build query
    query_params = {"user_id": player_id, "limit": limit}
    query = """
        SELECT s.*, m.title as map_title, m.artist as map_artist, 
               m.creator as map_creator, m.version as map_difficulty,
               u.name as player_name, u.country as player_country
        FROM scores s
        INNER JOIN maps m ON s.map_md5 = m.md5
        INNER JOIN users u ON s.userid = u.id
        WHERE s.userid = :user_id
    """
    
    if mode is not None:
        query += " AND s.mode = :mode"
        query_params["mode"] = mode
    
    query += " ORDER BY s.play_time DESC LIMIT :limit"
    
    data = await app.state.services.database.fetch_all(query, query_params)
    
    if not data:
        return responses.success([])
    
    response = [dict(rec) for rec in data]
    return responses.success(response)


@router.get("/players/{player_id}/best/{mode}")
async def get_player_best_scores(
    player_id: int,
    mode: int,
    limit: int = Query(100, ge=1, le=100),
) -> Success[list[dict]] | Failure:
    """Get player's best scores for a specific mode (top 100 by default)."""
    
    # Build query for best scores
    query = """
        SELECT s.*, m.title as map_title, m.artist as map_artist, 
               m.creator as map_creator, m.version as map_difficulty,
               u.name as player_name, u.country as player_country
        FROM scores s
        INNER JOIN maps m ON s.map_md5 = m.md5
        INNER JOIN users u ON s.userid = u.id
        WHERE s.userid = :user_id AND s.mode = :mode AND s.status = 2
        ORDER BY s.pp DESC
        LIMIT :limit
    """
    
    data = await app.state.services.database.fetch_all(
        query,
        {"user_id": player_id, "mode": mode, "limit": limit}
    )
    
    if not data:
        return responses.success([])
    
    response = [dict(rec) for rec in data]
    return responses.success(response)
