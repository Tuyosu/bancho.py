"""CORS and origin restriction middleware for API v2."""
from __future__ import annotations

from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware


# Allowed origins
ALLOWED_ORIGINS = [
    "https://osu-server-list.com",
    "https://www.osu-server-list.com",
]

# Discord bot user ID (hardcoded)
DISCORD_BOT_USER_ID = "1431332752644640768"


class APIAccessMiddleware(BaseHTTPMiddleware):
    """Middleware to restrict API access to specific origins and Discord bot."""
    
    async def dispatch(self, request: Request, call_next):
        # Skip non-API routes
        if not request.url.path.startswith("/api/v2"):
            return await call_next(request)
        
        # Check if request is from Discord bot (via custom header)
        discord_user_id = request.headers.get("X-Discord-User-ID")
        if discord_user_id == DISCORD_BOT_USER_ID:
            # Allow Discord bot access
            response = await call_next(request)
            return response
        
        # Check Origin header for web requests
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        
        # Allow requests from allowed origins
        if origin:
            if origin in ALLOWED_ORIGINS:
                response = await call_next(request)
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Discord-User-ID"
                return response
        
        # Check referer as fallback
        if referer:
            for allowed_origin in ALLOWED_ORIGINS:
                if referer.startswith(allowed_origin):
                    response = await call_next(request)
                    response.headers["Access-Control-Allow-Origin"] = allowed_origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Discord-User-ID"
                    return response
        
        # Handle OPTIONS preflight requests
        if request.method == "OPTIONS":
            # Check if origin is allowed
            if origin in ALLOWED_ORIGINS:
                from fastapi.responses import Response
                return Response(
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Credentials": "true",
                        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Discord-User-ID",
                    },
                )
        
        # Reject all other requests
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. API is only accessible from authorized origins.",
        )
