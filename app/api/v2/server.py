from __future__ import annotations

from fastapi import APIRouter
from fastapi import status

import app.state
from app.api.v2 import responses
from app.api.v2.models import responses as model_responses
from app.api.v2.models.server import PPSystemConfig
from app.api.v2.models.server import ServerStats

router = APIRouter()


@router.get("/server/stats")
async def get_server_stats() -> model_responses.Success[ServerStats]:
    """Get server statistics and PP system configuration."""
    
    # Get total users
    total_users = await app.state.services.database.fetch_val(
        "SELECT COUNT(*) FROM users",
        column=0,
    )
    
    # Get online users
    online_users = len([p for p in app.state.sessions.players if not p.is_bot_client])
    
    # Get total scores
    total_scores = await app.state.services.database.fetch_val(
        "SELECT COUNT(*) FROM scores",
        column=0,
    )
    
    # Get total maps
    total_maps = await app.state.services.database.fetch_val(
        "SELECT COUNT(*) FROM maps",
        column=0,
    )
    
    # Get ranked maps
    ranked_maps = await app.state.services.database.fetch_val(
        "SELECT COUNT(*) FROM maps WHERE status = 2",
        column=0,
    )
    
    # Get total playtime (sum of all playtime across all modes)
    total_playtime = await app.state.services.database.fetch_val(
        "SELECT SUM(playtime) FROM stats",
        column=0,
    ) or 0
    
    # PP system configuration
    pp_system = PPSystemConfig(
        aim_multiplier=0.75,
        speed_multiplier=1.25,
        accuracy_multiplier=1.20,
        flashlight_multiplier=0.60,
        miss_penalty_multiplier=1.15,
        global_multiplier=1.25,
        standard_pp_cap=47500,
        relax_pp_cap=47500,
        autopilot_pp_cap=20000,
    )
    
    response = ServerStats(
        total_users=total_users or 0,
        online_users=online_users,
        total_scores=total_scores or 0,
        total_maps=total_maps or 0,
        ranked_maps=ranked_maps or 0,
        total_playtime=total_playtime,
        pp_system=pp_system,
    )
    
    return responses.success(response)
