"""Rate limiting (slowapi): requests per client IP per minute.

- POST /api/auth/login: rate_limit_login (10/minute) - slows down password guessing
- POST /api/uploads:    rate_limit_upload (20/minute)
- everything else:      rate_limit_default (300/minute)

Counters live in this process's memory: they reset when the API restarts and are not
shared between several API processes (a shared store such as Redis would fix that).
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.errors import error_body
from app.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default],
                  enabled=settings.rate_limit_enabled)


async def rate_limit_exceeded(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content=error_body(
        "RATE_LIMITED", "Too many requests. Please wait a minute and try again.", {"limit": str(exc.detail)}))
