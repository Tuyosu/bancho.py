#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from collections.abc import Awaitable
from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import TypeVar

import databases
from rosu_pp_py import Beatmap
from rosu_pp_py import Performance
from redis import asyncio as aioredis

sys.path.insert(0, os.path.abspath(os.pardir))
os.chdir(os.path.abspath(os.pardir))

try:
    import app.settings
    import app.state.services
    from app.constants.gamemodes import GameMode
    from app.constants.mods import Mods
    from app.constants.privileges import Privileges
    from app.objects.beatmap import ensure_osu_file_is_available
except ModuleNotFoundError:
    print("\x1b[;91mMust run from tools/ directory\x1b[m")
    raise

T = TypeVar("T")

debug_mode_enabled = True

DEBUG = True

BEATMAPS_PATH = Path.cwd() / ".data/osu"


@dataclass
class Context:
    database: databases.Database
    redis: aioredis.Redis
    beatmaps: dict[int, Beatmap] = field(default_factory=dict)
    log_file: Any = None  # File handle for logging
    score_changes: list[dict] = field(default_factory=list)
    user_changes: list[dict] = field(default_factory=list)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())


def divide_chunks(values: list[T], n: int) -> Iterator[list[T]]:
    for i in range(0, len(values), n):
        yield values[i : i + n]

async def recalculate_score(
    score: dict[str, Any],
    beatmap_path: Path,
    ctx: Context,
) -> None:
    try:
        beatmap = ctx.beatmaps.get(score["map_id"])
        if beatmap is None:
            beatmap = Beatmap(path=str(beatmap_path))
            ctx.beatmaps[score["map_id"]] = beatmap

        # Check if Relax mod is active (Relax = 128)
        is_relax = bool(score["mods"] & 128)
        
        # Adjust miss penalty based on mod
        if is_relax:
            MISS_PENALTY_MULTIPLIER = 1.05  # Relax: 5% more hurting
        else:
            MISS_PENALTY_MULTIPLIER = 1.00  # Normal: No penalty
        
        adjusted_misses = int(score["nmiss"] * MISS_PENALTY_MULTIPLIER) if score["nmiss"] else 0

        calculator = Performance(
            mods=score["mods"],
            combo=score["max_combo"],
            n_geki=score["ngeki"],  # Mania 320s
            n300=score["n300"],
            n_katu=score["nkatu"],  # Mania 200s, Catch tiny droplets
            n100=score["n100"],
            n50=score["n50"],
            misses=adjusted_misses,  # Use adjusted miss count with penalty
        )
        attrs = calculator.calculate(beatmap)

        # Custom multipliers matching performance.py
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
        score_acc = score.get('acc', 100.0)
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
        pp_aim = (attrs.pp_aim or 0.0) * AIM_MULTIPLIER
        pp_speed = (attrs.pp_speed or 0.0) * SPEED_MULTIPLIER
        pp_flashlight = (attrs.pp_flashlight or 0.0) * FLASHLIGHT_MULTIPLIER
        
        # Estimate accuracy PP
        base_total = attrs.pp or 0.0
        base_aim = attrs.pp_aim or 0.0
        base_speed = attrs.pp_speed or 0.0
        base_flashlight = attrs.pp_flashlight or 0.0
        pp_acc_estimated = max(0.0, base_total - base_aim - base_speed - base_flashlight)
        pp_acc = pp_acc_estimated * ACCURACY_MULTIPLIER
        
        # Recalculate total PP from modified components
        pp_recalculated = pp_aim + pp_speed + pp_acc + pp_flashlight
        
        # Apply global multiplier
        CUSTOM_PP_MULTIPLIER = 1.25
        new_pp: float = pp_recalculated * CUSTOM_PP_MULTIPLIER
        
        # Apply map-specific nerf (speed-up maps, specific mappers, etc.)
        # Import here to avoid circular dependency
        from app.constants.nerfed_maps import should_nerf_map
        if "title" in score and "artist" in score and "creator" in score and "set_id" in score:
            map_nerf_multiplier = should_nerf_map(
                score["title"], 
                score["artist"], 
                score["creator"], 
                score["set_id"],
                mods=score["mods"]  # Pass mods to enable Relax-specific nerfs
            )
            new_pp = new_pp * map_nerf_multiplier
        
        # Apply CS nerf for Relax mode only (25% nerf for CS > 6)
        if is_relax and beatmap.cs > 6:
            CS_NERF_MULTIPLIER = 0.75  # 25% nerf
            new_pp = new_pp * CS_NERF_MULTIPLIER
        
        # Apply length buff/nerf (reward longer maps, punish very short maps)
        # Nerf: 10% nerf for maps < 1min
        # Buff: 5% at 3min, 10% at 4min, 15% at 5min+
        map_length_seconds = score.get("total_length", 0)  # Total length from database
        if map_length_seconds < 60:  # Less than 1 minute
            LENGTH_NERF_MULTIPLIER = 0.90  # 10% nerf
            new_pp = new_pp * LENGTH_NERF_MULTIPLIER
        elif map_length_seconds >= 180:  # 3 minutes or more
            if map_length_seconds >= 300:  # 5+ minutes
                LENGTH_BUFF_MULTIPLIER = 1.15  # 15% buff
            elif map_length_seconds >= 240:  # 4-5 minutes
                LENGTH_BUFF_MULTIPLIER = 1.10  # 10% buff
            else:  # 3-4 minutes
                LENGTH_BUFF_MULTIPLIER = 1.05  # 5% buff
            new_pp = new_pp * LENGTH_BUFF_MULTIPLIER
        
        # Apply PP caps
        PP_CAPS = {
            0: 55000,  # Standard
            4: 55000,  # Relax
            8: 20000,  # Autopilot
        }
        if score["mode"] in PP_CAPS and new_pp > PP_CAPS[score["mode"]]:
            new_pp = float(PP_CAPS[score["mode"]])
        
        # Apply player-specific buffs
        # Configure player buffs here: {player_id: multiplier}
        PLAYER_BUFFS = {
            # Add players as needed
        }
        
        if "userid" in score and score["userid"] in PLAYER_BUFFS:
            new_pp = new_pp * PLAYER_BUFFS[score["userid"]]

        
        if math.isnan(new_pp) or math.isinf(new_pp):
            new_pp = 0.0

        await ctx.database.execute(
            "UPDATE scores SET pp = :new_pp WHERE id = :id",
            {"new_pp": new_pp, "id": score["id"]},
        )

        # Log the change
        if ctx.log_file:
            is_relax = bool(score["mods"] & 128)
            change_record = {
                "score_id": score["id"],
                "old_pp": round(score["pp"], 3),
                "new_pp": round(new_pp, 3),
                "change": round(new_pp - score["pp"], 3),
                "map": f"{score.get('artist', 'Unknown')} - {score.get('title', 'Unknown')} [{score.get('creator', 'Unknown')}]",
                "mods": score["mods"],
                "is_relax": is_relax,
                "mode": score["mode"]
            }
            ctx.score_changes.append(change_record)
        
        if debug_mode_enabled:
            print(
                f"Recalculated score ID {score['id']} ({score['pp']:.3f}pp -> {new_pp:.3f}pp)",
            )
            
    except Exception as e:
        # Log the error and continue processing other scores
        print(f"Failed to recalculate score ID {score['id']}: {e}")


async def process_score_chunk(
    chunk: list[dict[str, Any]],
    ctx: Context,
) -> None:
    tasks: list[Awaitable[None]] = []
    for score in chunk:
        osu_file_available = await ensure_osu_file_is_available(
            score["map_id"],
            expected_md5=score["map_md5"],
        )
        if osu_file_available:
            tasks.append(
                recalculate_score(
                    score,
                    BEATMAPS_PATH / f"{score['map_id']}.osu",
                    ctx,
                ),
            )

    await asyncio.gather(*tasks)


async def recalculate_user(
    id: int,
    game_mode: GameMode,
    ctx: Context,
) -> None:
    best_scores = await ctx.database.fetch_all(
        "SELECT s.pp, s.acc FROM scores s "
        "INNER JOIN maps m ON s.map_md5 = m.md5 "
        "WHERE s.userid = :user_id AND s.mode = :mode "
        "AND s.status = 2 AND m.status IN (2, 3) "  # ranked, approved
        "ORDER BY s.pp DESC",
        {"user_id": id, "mode": game_mode},
    )

    total_scores = len(best_scores)
    if not total_scores:
        return

    # calculate new total weighted accuracy
    weighted_acc = sum(row["acc"] * 0.95**i for i, row in enumerate(best_scores))
    bonus_acc = 100.0 / (20 * (1 - 0.95**total_scores))
    acc = (weighted_acc * bonus_acc) / 100

    # calculate new total weighted pp
    weighted_pp = sum(row["pp"] * 0.95**i for i, row in enumerate(best_scores))
    bonus_pp = 416.6667 * (1 - 0.9994**total_scores)
    pp = round(weighted_pp + bonus_pp)

    # Use INSERT...ON DUPLICATE KEY UPDATE to handle missing stats records
    await ctx.database.execute(
        """
        INSERT INTO stats (id, mode, pp, acc, plays, tscore, rscore, playtime, max_combo, total_hits, xh_count, x_count, sh_count, s_count, a_count)
        VALUES (:id, :mode, :pp, :acc, :plays, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        ON DUPLICATE KEY UPDATE pp = :pp, acc = :acc, plays = :plays
        """,
        {"pp": pp, "acc": acc, "id": id, "mode": game_mode, "plays": total_scores},
    )

    user_info = await ctx.database.fetch_one(
        "SELECT country, priv FROM users WHERE id = :id",
        {"id": id},
    )
    if user_info is None:
        raise Exception(f"Unknown user ID {id}?")

    if user_info["priv"] & Privileges.UNRESTRICTED:
        await ctx.redis.zadd(
            f"bancho:leaderboard:{game_mode.value}",
            {str(id): pp},
        )

        await ctx.redis.zadd(
            f"bancho:leaderboard:{game_mode.value}:{user_info['country']}",
            {str(id): pp},
        )
        
    # Log user stat change
    if ctx.log_file:
        user_record = {
            "user_id": id,
            "pp": round(pp, 3),
            "acc": round(acc, 3),
            "mode": game_mode.value,
            "total_scores": total_scores
        }
        ctx.user_changes.append(user_record)
    
    if debug_mode_enabled:
        print(f"Recalculated user ID {id} ({pp:.3f}pp, {acc:.3f}%)")

async def process_user_chunk(
    chunk: list[int],
    game_mode: GameMode,
    ctx: Context,
) -> None:
    tasks: list[Awaitable[None]] = []
    for id in chunk:
        tasks.append(recalculate_user(id, game_mode, ctx))

    await asyncio.gather(*tasks)


async def recalculate_mode_users(mode: GameMode, ctx: Context) -> None:
    user_ids = [
        row["id"] for row in await ctx.database.fetch_all("SELECT id FROM users")
    ]

    for id_chunk in divide_chunks(user_ids, 100):
        await process_user_chunk(id_chunk, mode, ctx)


async def recalculate_mode_scores(mode: GameMode, ctx: Context) -> None:
    scores = [
        dict(row)
        for row in await ctx.database.fetch_all(
            """\
            SELECT scores.id, scores.userid, scores.mode, scores.mods, scores.map_md5,
              scores.pp, scores.acc, scores.max_combo,
              scores.ngeki, scores.n300, scores.nkatu, scores.n100, scores.n50, scores.nmiss,
              maps.id as `map_id`, maps.title, maps.artist, maps.creator, maps.set_id, maps.total_length
            FROM scores
            INNER JOIN maps ON scores.map_md5 = maps.md5
            WHERE scores.status = 2
              AND scores.mode = :mode
            ORDER BY scores.pp DESC
            """,
            {"mode": mode},
        )
    ]

    for score_chunk in divide_chunks(scores, 100):
        await process_score_chunk(score_chunk, ctx)


def write_log_file(ctx: Context, modes: list[str], no_scores: bool, no_stats: bool) -> None:
    """Write detailed log file with all recalculation changes."""
    if not ctx.log_file:
        return
    
    end_time = datetime.now().isoformat()
    
    # Write header
    ctx.log_file.write("=" * 80 + "\n")
    ctx.log_file.write("PP RECALCULATION LOG\n")
    ctx.log_file.write("=" * 80 + "\n\n")
    
    # Write metadata
    ctx.log_file.write(f"Start Time: {ctx.start_time}\n")
    ctx.log_file.write(f"End Time: {end_time}\n")
    ctx.log_file.write(f"Modes: {', '.join(modes)}\n")
    ctx.log_file.write(f"Recalculate Scores: {not no_scores}\n")
    ctx.log_file.write(f"Recalculate Stats: {not no_stats}\n")
    ctx.log_file.write("\n")
    
    # Write score changes
    if ctx.score_changes:
        ctx.log_file.write("=" * 80 + "\n")
        ctx.log_file.write(f"SCORE CHANGES ({len(ctx.score_changes)} total)\n")
        ctx.log_file.write("=" * 80 + "\n\n")
        
        for change in ctx.score_changes:
            ctx.log_file.write(f"Score ID: {change['score_id']}\n")
            ctx.log_file.write(f"  Map: {change['map']}\n")
            ctx.log_file.write(f"  Mode: {change['mode']} | Mods: {change['mods']} | Relax: {change['is_relax']}\n")
            ctx.log_file.write(f"  PP Change: {change['old_pp']:.3f}pp -> {change['new_pp']:.3f}pp ")
            ctx.log_file.write(f"({'+' if change['change'] >= 0 else ''}{change['change']:.3f}pp)\n")
            ctx.log_file.write("\n")
    
    # Write user stat changes
    if ctx.user_changes:
        ctx.log_file.write("=" * 80 + "\n")
        ctx.log_file.write(f"USER STAT UPDATES ({len(ctx.user_changes)} total)\n")
        ctx.log_file.write("=" * 80 + "\n\n")
        
        for user in ctx.user_changes:
            ctx.log_file.write(f"User ID: {user['user_id']}\n")
            ctx.log_file.write(f"  Mode: {user['mode']}\n")
            ctx.log_file.write(f"  PP: {user['pp']:.3f}pp\n")
            ctx.log_file.write(f"  Accuracy: {user['acc']:.3f}%\n")
            ctx.log_file.write(f"  Total Scores: {user['total_scores']}\n")
            ctx.log_file.write("\n")
    
    # Write summary
    ctx.log_file.write("=" * 80 + "\n")
    ctx.log_file.write("SUMMARY\n")
    ctx.log_file.write("=" * 80 + "\n\n")
    ctx.log_file.write(f"Total Scores Recalculated: {len(ctx.score_changes)}\n")
    ctx.log_file.write(f"Total Users Updated: {len(ctx.user_changes)}\n")
    
    if ctx.score_changes:
        total_pp_change = sum(c['change'] for c in ctx.score_changes)
        avg_pp_change = total_pp_change / len(ctx.score_changes)
        ctx.log_file.write(f"Total PP Change: {'+' if total_pp_change >= 0 else ''}{total_pp_change:.3f}pp\n")
        ctx.log_file.write(f"Average PP Change: {'+' if avg_pp_change >= 0 else ''}{avg_pp_change:.3f}pp\n")
    
    ctx.log_file.write("\n" + "=" * 80 + "\n")
    ctx.log_file.write("END OF LOG\n")
    ctx.log_file.write("=" * 80 + "\n")


async def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Recalculate performance for scores and/or stats",
    )

    parser.add_argument(
        "-d",
        "--debug",
        help="Enable debug logging",
        action="store_true",
    )
    parser.add_argument(
        "--no-scores",
        help="Disable recalculating scores",
        action="store_true",
    )
    parser.add_argument(
        "--no-stats",
        help="Disable recalculating user stats",
        action="store_true",
    )

    parser.add_argument(
        "-m",
        "--mode",
        nargs=argparse.ONE_OR_MORE,
        required=False,
        default=["0", "1", "2", "3", "4", "5", "6", "8"],
        # would love to do things like "vn!std", but "!" will break interpretation
        choices=["0", "1", "2", "3", "4", "5", "6", "8"],
    )
    args = parser.parse_args(argv)

    global debug_mode_enabled
    debug_mode_enabled = args.debug

    # Create log file
    log_dir = Path.cwd() / "logs" / "recalc"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = log_dir / f"recalc_{timestamp}.log"
    
    log_file = open(log_filename, "w", encoding="utf-8")
    print(f"Logging to: {log_filename}")

    db = databases.Database(app.settings.DB_DSN)
    await db.connect()

    redis = await aioredis.from_url(app.settings.REDIS_DSN)  # type: ignore[no-untyped-call]

    ctx = Context(db, redis, log_file=log_file)

    for mode in args.mode:
        mode = GameMode(int(mode))

        if not args.no_scores:
            await recalculate_mode_scores(mode, ctx)

        if not args.no_stats:
            await recalculate_mode_users(mode, ctx)

    # Write log file
    write_log_file(ctx, args.mode, args.no_scores, args.no_stats)
    
    if ctx.log_file:
        ctx.log_file.close()
        print(f"\nLog file saved: {log_filename}")
    
    await app.state.services.http_client.aclose()
    await db.disconnect()
    await redis.aclose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
