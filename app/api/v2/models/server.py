from __future__ import annotations

from . import BaseModel


class ServerStats(BaseModel):
    """Server statistics model."""
    
    total_users: int
    online_users: int
    total_scores: int
    total_maps: int
    ranked_maps: int
    total_playtime: int
    
    # PP system configuration
    pp_system: PPSystemConfig


class PPSystemConfig(BaseModel):
    """PP system configuration."""
    
    aim_multiplier: float
    speed_multiplier: float
    accuracy_multiplier: float
    flashlight_multiplier: float
    miss_penalty_multiplier: float
    global_multiplier: float
    
    # PP caps
    standard_pp_cap: int
    relax_pp_cap: int
    autopilot_pp_cap: int
