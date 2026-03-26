"""
AI Fitness Coach — Rate Limiting Configuration

Shared limiter instance used across all routers.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request


def _get_rate_limit_key(request: Request) -> str:
    """Rate limit by user_id from JWT if available, otherwise by IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.services.auth import decode_token
            payload = decode_token(auth.split(" ", 1)[1])
            return payload.get("sub", get_remote_address(request))
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_rate_limit_key)
