"""bancho.py's v2 apis for leaderboards"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import status
from fastapi.param_functions import Query

import app.state
from app.api.v2.common import responses
from app.api.v2.common.responses import Failure
from app.api.v2.common.responses import Success

router = APIRouter()


@router.get("/leaderboard/{mode}")
async def get_leaderboard(
    mode: int,
    country: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> Success[list[dict]] | Failure:
    """Get global or country leaderboard for a specific mode."""
    
    offset = (page - 1) * page_size
    
    # Build query
    query = """
        SELECT 
            s.id as user_id,
            s.pp,
            s.acc,
            s.plays,
            s.playtime,
            s.max_combo,
            s.total_hits,
            s.xh_count,
            s.x_count,
            s.sh_count,
            s.s_count,
            s.a_count,
            u.name as player_name,
            u.country,
            u.clan_id,
            ROW_NUMBER() OVER (ORDER BY s.pp DESC) as `rank`
        FROM stats s
        INNER JOIN users u ON s.id = u.id
        WHERE s.mode = :mode AND u.priv & 1
    """
    
    params = {"mode": mode, "limit": page_size, "offset": offset}
    
    if country:
        query += " AND u.country = :country"
        params["country"] = country
    
    query += " ORDER BY s.pp DESC LIMIT :limit OFFSET :offset"
    
    data = await app.state.services.database.fetch_all(query, params)
    
    # Get total count
    count_query = """
        SELECT COUNT(*) as total
        FROM stats s
        INNER JOIN users u ON s.id = u.id
        WHERE s.mode = :mode AND u.priv & 1
    """
    
    if country:
        count_query += " AND u.country = :country"
    
    total = await app.state.services.database.fetch_val(
        count_query,
        {"mode": mode, "country": country} if country else {"mode": mode},
        column=0,
    ) or 0
    
    response = [dict(rec) for rec in data]
    
    return responses.success(
        response,
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )
