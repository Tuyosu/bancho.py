#!/usr/bin/env python3
"""
Recalculate all user stats after unranking high CS maps.
This will remove PP from scores on unranked maps (CS >= 7).
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import app.state
from app.logging import Ansi, log


async def main():
    """Recalculate stats for all users in all modes."""
    from app.repositories import stats as stats_repo
    
    log("Starting full stats recalculation...", Ansi.LCYAN)
    
    # Get all unique user IDs from stats table
    users = await app.state.services.database.fetch_all(
        "SELECT DISTINCT id FROM stats"
    )
    
    total_users = len(users)
    log(f"Found {total_users} users to recalculate", Ansi.LGREEN)
    
    # Recalculate for modes 0 (VN) and 4 (RX)
    modes = [0, 4]
    
    for idx, user_row in enumerate(users, 1):
        user_id = user_row["id"]
        
        for mode in modes:
            try:
                await stats_repo.sql_recalculate_mode(user_id, mode)
            except Exception as e:
                log(f"Error recalculating user {user_id} mode {mode}: {e}", Ansi.LRED)
        
        if idx % 10 == 0:
            log(f"Progress: {idx}/{total_users} users recalculated", Ansi.LCYAN)
    
    log(f"Stats recalculation complete! Processed {total_users} users", Ansi.LGREEN)


if __name__ == "__main__":
    asyncio.run(main())
