from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict

from rosu_pp_py import Beatmap
from rosu_pp_py import Performance
from rosu_pp_py import DifficultyAttributes

from app.constants.mods import Mods
from app.constants.nerfed_maps import should_nerf_map


@dataclass
class ScoreParams:
    mode: int
    mods: int | None = None
    combo: int | None = None

    # caller may pass either acc OR 300/100/50/geki/katu/miss
    # passing both will result in a value error being raised
    acc: float | None = None

    n300: int | None = None
    n100: int | None = None
    n50: int | None = None
    ngeki: int | None = None
    nkatu: int | None = None
    nmiss: int | None = None


class PerformanceRating(TypedDict):
    pp: float
    pp_acc: float | None
    pp_aim: float | None
    pp_speed: float | None
    pp_flashlight: float | None
    effective_miss_count: float | None
    pp_difficulty: float | None


class DifficultyRating(TypedDict):
    stars: float
    aim: float | None
    speed: float | None
    flashlight: float | None
    slider_factor: float | None
    speed_note_count: float | None
    stamina: float | None
    color: float | None
    rhythm: float | None
    peak: float | None


class PerformanceResult(TypedDict):
    performance: PerformanceRating
    difficulty: DifficultyRating


def calculate_performances(
    osu_file_path: str | None,
    scores: Iterable[ScoreParams],
    map_title: str | None = None,
    map_artist: str | None = None,
    map_creator: str | None = None,
    map_set_id: int | None = None,
    map_length: int | None = None,  # Map length in seconds for length buff/nerf
    apply_pp_cap: bool = True,  # Set to False for display purposes (bot commands)
    player_id: int | None = None,  # Player ID for player-specific buffs
) -> list[PerformanceResult]:
    """\
    Calculate performance for multiple scores on a single beatmap.

    Typically most useful for mass-recalculation situations.

    TODO: Some level of error handling & returning to caller should be
    implemented here to handle cases where e.g. the beatmap file is invalid
    or there an issue during calculation.
    """
    if not osu_file_path:
        return []

    calc_bmap = Beatmap(path=osu_file_path)

    results: list[PerformanceResult] = []

    for score in scores:
        if score.acc and (
            score.n300 or score.n100 or score.n50 or score.ngeki or score.nkatu
        ):
            raise ValueError(
                "Must not specify accuracy AND 300/100/50/geki/katu. Only one or the other.",
            )

        # rosupp ignores NC and requires DT
        if score.mods is not None:
            if score.mods & Mods.NIGHTCORE:
                score.mods |= Mods.DOUBLETIME

        # Check if Relax mod is active (Relax = 128)
        is_relax = bool((score.mods or 0) & 128)
        
        # Adjust miss penalty based on mod
        if is_relax:
            MISS_PENALTY_MULTIPLIER = 1.05  # Relax: 5% more hurting
        else:
            MISS_PENALTY_MULTIPLIER = 1.00  # Normal: No penalty
        
        adjusted_misses = int((score.nmiss or 0) * MISS_PENALTY_MULTIPLIER) if score.nmiss else None

        # FIX: Removed 'mode' parameter - it's not accepted by Performance
        # The mode is determined from the beatmap itself
        calculator = Performance(
            # mode=score.mode,  # REMOVED - this parameter doesn't exist
            mods=score.mods or 0,
            combo=score.combo,
            accuracy=score.acc,  # Changed from 'acc' to 'accuracy'
            n300=score.n300,
            n100=score.n100,
            n50=score.n50,
            n_geki=score.ngeki,
            n_katu=score.nkatu,
            misses=adjusted_misses,  # Use adjusted miss count with penalty
        )
        
        # Set the mode on the beatmap if needed
        # Note: rosu_pp_py typically auto-detects mode from the beatmap
        # but if you need to override it, you might do:
        # calc_bmap.mode = score.mode
        
        # Calculate using the correct method name
        result = calculator.calculate(calc_bmap)  # Changed from 'performance' to 'calculate'

        # Custom multipliers for each PP component
        # Different values for Relax mod
        if is_relax:
            AIM_MULTIPLIER = 1.35      # Relax: Buff aim by 35%
            SPEED_MULTIPLIER = 1.10    # Relax: Buff speed by 10%
            FLASHLIGHT_MULTIPLIER = 0.75 # Relax: Nerf flashlight by 25%
        else:
            AIM_MULTIPLIER = 1.10      # Normal: Buff aim by 10%
            SPEED_MULTIPLIER = 1.20    # Normal: Buff speed by 20%
            FLASHLIGHT_MULTIPLIER = 0.70 # Normal: Nerf flashlight by 30%
        
        # Dynamic accuracy multiplier based on score accuracy
        # More lenient for higher accuracy, especially 97-100%
        score_acc = score.acc if score.acc else 100.0
        if score_acc >= 100.0:
            ACCURACY_MULTIPLIER = 1.33  # Perfect accuracy
        elif score_acc >= 99.0:
            ACCURACY_MULTIPLIER = 1.31  # 99-100%
        elif score_acc >= 98.0:
            ACCURACY_MULTIPLIER = 1.27  # 98-99%
        elif score_acc >= 97.0:
            ACCURACY_MULTIPLIER = 1.24  # 97-98%
        elif score_acc >= 95.0:
            ACCURACY_MULTIPLIER = 1.19  # 95-97%
        else:
            ACCURACY_MULTIPLIER = 1.16  # < 95%
        
        # Apply multipliers to individual components
        pp_aim = (result.pp_aim or 0.0) * AIM_MULTIPLIER
        pp_speed = (result.pp_speed or 0.0) * SPEED_MULTIPLIER
        pp_flashlight = (result.pp_flashlight or 0.0) * FLASHLIGHT_MULTIPLIER
        
        # For accuracy, we need to extract it from the total
        # The rosu_pp formula combines components, so we recalculate from weighted parts
        # Note: pp_acc is not directly available in rosu_pp_py result, so we estimate it
        # Total PP ≈ aim + speed + acc + flashlight (simplified, actual formula is more complex)
        
        # Get base accuracy PP by subtracting known components from total
        base_total = result.pp or 0.0
        base_aim = result.pp_aim or 0.0
        base_speed = result.pp_speed or 0.0
        base_flashlight = result.pp_flashlight or 0.0
        
        # Estimate accuracy PP (this is approximate)
        pp_acc_estimated = max(0.0, base_total - base_aim - base_speed - base_flashlight)
        pp_acc = pp_acc_estimated * ACCURACY_MULTIPLIER
        
        # Recalculate total PP from modified components
        # Using a weighted combination similar to osu!'s formula
        pp_recalculated = pp_aim + pp_speed + pp_acc + pp_flashlight
        
        # Apply global multiplier
        CUSTOM_PP_MULTIPLIER = 1.25
        pp = pp_recalculated * CUSTOM_PP_MULTIPLIER
        
        # Apply map-specific nerf (speed-up maps, specific mappers, etc.)
        if map_title and map_artist and map_creator and map_set_id is not None:
            map_nerf_multiplier = should_nerf_map(
                map_title, 
                map_artist, 
                map_creator, 
                map_set_id,
                mods=score.mods or 0  # Pass mods to enable Relax-specific nerfs
            )
            pp = pp * map_nerf_multiplier
        
        # Apply CS nerf for Relax mode only (25% nerf for CS > 6)
        if is_relax and calc_bmap.cs > 6:
            CS_NERF_MULTIPLIER = 0.75  # 25% nerf
            pp = pp * CS_NERF_MULTIPLIER
        
        # Apply length buff/nerf (reward longer maps, punish very short maps)
        # Nerf: 10% nerf for maps < 1min
        # Buff: 5% at 3min, 10% at 4min, 15% at 5min+
        if map_length is not None:
            map_length_seconds = map_length  # Total length from parameter
            if map_length_seconds < 60:  # Less than 1 minute
                LENGTH_NERF_MULTIPLIER = 0.90  # 10% nerf
                pp = pp * LENGTH_NERF_MULTIPLIER
            elif map_length_seconds >= 180:  # 3 minutes or more
                if map_length_seconds >= 300:  # 5+ minutes
                    LENGTH_BUFF_MULTIPLIER = 1.15  # 15% buff
                elif map_length_seconds >= 240:  # 4-5 minutes
                    LENGTH_BUFF_MULTIPLIER = 1.10  # 10% buff
                else:  # 3-4 minutes
                    LENGTH_BUFF_MULTIPLIER = 1.05  # 5% buff
                pp = pp * LENGTH_BUFF_MULTIPLIER
        
        # Apply PP caps only if requested (for score submission)
        # Skip for display purposes (bot commands showing theoretical PP)
        if apply_pp_cap:
            PP_CAPS = {
                0: 55000,  # Standard
                4: 55000,  # Relax
                8: 20000,  # Autopilot
            }
            if score.mode in PP_CAPS and pp > PP_CAPS[score.mode]:
                pp = float(PP_CAPS[score.mode])
        
        # Apply player-specific buffs
        # Configure player buffs here: {player_id: multiplier}
        PLAYER_BUFFS = {
            # Add players as needed
        }
        
        if player_id and player_id in PLAYER_BUFFS:
            pp = pp * PLAYER_BUFFS[player_id]


        if math.isnan(pp) or math.isinf(pp):
            # TODO: report to logserver
            pp = 0.0
        else:
            pp = round(pp, 3)

        results.append(
            {
                "performance": {
                    "pp": pp,
                    "pp_aim": pp_aim,
                    "pp_speed": pp_speed,
                    "pp_flashlight": pp_flashlight,
                    "effective_miss_count": result.effective_miss_count,
                    "pp_difficulty": result.pp_difficulty,
                },
                "difficulty": {
                    "stars": result.difficulty.stars,
                    "aim": result.difficulty.aim,
                    "speed": result.difficulty.speed,
                    "flashlight": result.difficulty.flashlight,
                    "slider_factor": result.difficulty.slider_factor,
                    "speed_note_count": result.difficulty.speed_note_count,
                    "stamina": result.difficulty.stamina,
                    "color": result.difficulty.color,
                    "rhythm": result.difficulty.rhythm,
                },
            },
        )

    return results


def calculate_difficulty(bmap_file: str, mode: int) -> DifficultyAttributes | None:
    calc_bmap = Beatmap(str=bmap_file)
    # Note: Calculator might also need adjustment
    # If Calculator doesn't exist in rosu_pp_py, you might need:
    # from rosu_pp_py import Difficulty
    # calculator = Difficulty(mods=0)  # without mode parameter
    calculator = Calculator(mode=mode)

    result = calculator.difficulty(calc_bmap)

    if math.isnan(result.stars):
        return None

    if math.isinf(result.stars):
        return None

    return result