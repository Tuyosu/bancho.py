#!/usr/bin/env python3
"""Quick script to recalculate stats for all users using the new sql_recalculate_mode function."""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

import app.settings
import app.state.services
from app.repositories import stats as stats_repo

async def main():
    """Recalculate stats for all users in all modes."""
    import databases
    
    db = databases.Database(app.settings.DB_DSN)
    await db.connect()
    
    # Initialize the database service
    app.state.services.database = db
    
    # Get all user IDs
    users = await db.fetch_all("SELECT DISTINCT id FROM users")
    
    # Modes to recalculate: 0=std, 4=relax std
    modes = [0, 4]
    
    total_users = len(users)
    print(f"Recalculating stats for {total_users} users in modes {modes}...")
    
    for idx, user in enumerate(users, 1):
        user_id = user['id']
        
        for mode in modes:
            try:
                await stats_repo.sql_recalculate_mode(user_id, mode)
                print(f"[{idx}/{total_users}] Recalculated user {user_id} mode {mode}")
            except Exception as e:
                print(f"[{idx}/{total_users}] Error recalculating user {user_id} mode {mode}: {e}")
    
    await db.disconnect()
    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
