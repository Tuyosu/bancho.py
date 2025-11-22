from __future__ import annotations

from datetime import datetime

from . import BaseModel

# input models


# output models


class Score(BaseModel):
    id: int
    map_md5: str
    userid: int

    score: int
    pp: float
    acc: float
    max_combo: int
    mods: int

    n300: int
    n100: int
    n50: int
    nmiss: int
    ngeki: int
    nkatu: int

    grade: str
    status: int
    mode: int

    play_time: datetime
    time_elapsed: int
    perfect: bool

    # Extended fields (optional for backward compatibility)
    pp_aim: float | None = None
    pp_speed: float | None = None
    pp_accuracy: float | None = None
    pp_flashlight: float | None = None
    
    map_title: str | None = None
    map_artist: str | None = None
    map_creator: str | None = None
    map_difficulty: str | None = None
    map_stars: float | None = None
    
    player_name: str | None = None
    player_country: str | None = None
    
    global_rank: int | None = None
    country_rank: int | None = None
