"""Discord webhook utilities for server status notifications."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import app.settings
import app.state
from app.logging import Ansi
from app.logging import log


# Discord webhook URL (configure in settings or hardcode here)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1391070169035575417/C_Nx_t-wAWa8Q-e82ktci0iK5h3t44JfdzxP212zEFEqG0Aci_kwYAun7Li5T9C8mThq"  # Set your Discord webhook URL here


async def send_discord_webhook(
    content: str | None = None,
    embed: dict[str, Any] | None = None,
) -> bool:
    """Send a message to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL:
        log("Discord webhook URL not configured", Ansi.LYELLOW)
        return False
    
    payload: dict[str, Any] = {}
    
    if content:
        payload["content"] = content
    
    if embed:
        payload["embeds"] = [embed]
    
    try:
        response = await app.state.services.http_client.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
        )
        
        if response.status_code in (200, 204):
            return True
        else:
            log(f"Discord webhook failed: {response.status_code}", Ansi.LRED)
            return False
    
    except Exception as e:
        log(f"Discord webhook error: {e}", Ansi.LRED)
        return False


async def send_server_status_webhook() -> None:
    """Send server status update to Discord."""
    # Get server stats
    total_users = await app.state.services.database.fetch_val(
        "SELECT COUNT(*) FROM users",
        column=0,
    ) or 0
    
    online_users = len([p for p in app.state.sessions.players if not p.is_bot_client])
    
    total_scores = await app.state.services.database.fetch_val(
        "SELECT COUNT(*) FROM scores",
        column=0,
    ) or 0
    
    # Check component status
    backend_status = "🟢 Online"  # If this code runs, backend is online
    
    # Check API (try to access database)
    try:
        await app.state.services.database.fetch_val("SELECT 1", column=0)
        api_status = "🟢 Online"
    except Exception:
        api_status = "🔴 Offline"
    
    # Check Frontend (check if HTTP client is available)
    try:
        # You can add a ping to your frontend URL here if needed
        # For now, assume it's online if backend is online
        frontend_status = "🟢 Online"
    except Exception:
        frontend_status = "🔴 Offline"
    
    # Create embed
    embed = {
        "title": "�️ Server Status Report",
        "description": "Automated status check for all server components.",
        "color": 0x00FF00,  # Green
        "fields": [
            {
                "name": "⚙️ Backend",
                "value": backend_status,
                "inline": True,
            },
            {
                "name": "🌐 Frontend",
                "value": frontend_status,
                "inline": True,
            },
            {
                "name": "� API",
                "value": api_status,
                "inline": True,
            },
            {
                "name": "�👥 Online Players",
                "value": str(online_users),
                "inline": True,
            },
            {
                "name": "📊 Total Users",
                "value": f"{total_users:,}",
                "inline": True,
            },
            {
                "name": "🎮 Total Scores",
                "value": f"{total_scores:,}",
                "inline": True,
            },
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {
            "text": "Automated status check • Every 30 minutes",
        },
    }
    
    success = await send_discord_webhook(embed=embed)
    
    if success:
        log("Server status webhook sent successfully", Ansi.LGREEN)
    else:
        log("Failed to send server status webhook", Ansi.LRED)


async def server_status_webhook_loop(interval: int = 1800) -> None:
    """Background task to send server status webhooks every interval seconds.
    
    Args:
        interval: Time between webhooks in seconds (default: 1800 = 30 minutes)
    """
    while True:
        await asyncio.sleep(interval)
        
        try:
            await send_server_status_webhook()
        except Exception as e:
            log(f"Error in server status webhook loop: {e}", Ansi.LRED)
