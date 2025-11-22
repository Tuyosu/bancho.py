# isort: dont-add-imports

from fastapi import APIRouter

from . import api_keys
from . import clans
from . import leaderboard
from . import maps
from . import players
from . import scores
from . import server

apiv2_router = APIRouter(tags=["API v2"], prefix="/v2")

apiv2_router.include_router(api_keys.router)
apiv2_router.include_router(clans.router)
apiv2_router.include_router(leaderboard.router)
apiv2_router.include_router(maps.router)
apiv2_router.include_router(players.router)
apiv2_router.include_router(scores.router)
apiv2_router.include_router(server.router)
