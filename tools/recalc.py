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

        # Buff miss penalty by 15% (make misses hurt more)
        MISS_PENALTY_MULTIPLIER = 1.15
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
        AIM_MULTIPLIER = 0.75      # Nerf aim by 25%
        SPEED_MULTIPLIER = 1.25    # Buff speed by 25%
        ACCURACY_MULTIPLIER = 1.20 # Buff accuracy by 20%
        FLASHLIGHT_MULTIPLIER = 0.60 # Nerf flashlight by 40%
        
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
                score["set_id"]
            )
            new_pp = new_pp * map_nerf_multiplier
        
        if math.isnan(new_pp) or math.isinf(new_pp):
            new_pp = 0.0

        await ctx.database.execute(
            "UPDATE scores SET pp = :new_pp WHERE id = :id",
            {"new_pp": new_pp, "id": score["id"]},
        )

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

    await ctx.database.execute(
        "UPDATE stats SET pp = :pp, acc = :acc WHERE id = :id AND mode = :mode",
        {"pp": pp, "acc": acc, "id": id, "mode": game_mode},
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
            SELECT scores.id, scores.mode, scores.mods, scores.map_md5,
              scores.pp, scores.acc, scores.max_combo,
              scores.ngeki, scores.n300, scores.nkatu, scores.n100, scores.n50, scores.nmiss,
              maps.id as `map_id`, maps.title, maps.artist, maps.creator, maps.set_id
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

    db = databases.Database(app.settings.DB_DSN)
    await db.connect()

    redis = await aioredis.from_url(app.settings.REDIS_DSN)  # type: ignore[no-untyped-call]

    ctx = Context(db, redis)

    for mode in args.mode:
        mode = GameMode(int(mode))

        if not args.no_scores:
            await recalculate_mode_scores(mode, ctx)

        if not args.no_stats:
            await recalculate_mode_users(mode, ctx)

    await app.state.services.http_client.aclose()
    await db.disconnect()
    await redis.aclose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
