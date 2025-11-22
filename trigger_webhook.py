#!/usr/bin/env python3
"""Manual trigger for server status webhook."""
import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/srv/root')

async def main():
    """Trigger the webhook manually."""
    # Import after path is set
    import app.state
    from app.webhooks import send_server_status_webhook
    
    # Initialize minimal required services
    from app.state.services import Database
    from app.state.services import Redis
    
    # Connect to database
    app.state.services.database = Database()
    await app.state.services.database.connect()
    
    # Initialize redis
    app.state.services.redis = Redis()
    await app.state.services.redis.initialize()
    
    # Initialize HTTP client
    import httpx
    app.state.services.http_client = httpx.AsyncClient()
    
    # Initialize sessions (for online player count)
    from app.objects.collections import Players
    app.state.sessions.players = Players()
    
    print("Sending webhook...")
    await send_server_status_webhook()
    print("Webhook sent!")
    
    # Cleanup
    await app.state.services.http_client.aclose()
    await app.state.services.database.disconnect()
    await app.state.services.redis.aclose()

if __name__ == "__main__":
    asyncio.run(main())
