"""
AI Fitness Coach v1 — Structured Logging

Provides:
- Correlation ID middleware (request-scoped UUID)
- Structured JSON-ish logger with context fields
- Decorators for timing and tracking API calls
"""
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional, Callable
from functools import wraps
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ─── Correlation ID ────────────────────────────────────────────
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="no-request")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique correlation ID to every request."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        token = correlation_id.set(req_id)
        
        start = time.time()
        response: Response = await call_next(request)
        elapsed = time.time() - start

        response.headers["X-Request-ID"] = req_id
        
        logger = get_logger("http")
        logger.info(
            "request_complete",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed * 1000),
        )
        
        correlation_id.reset(token)
        return response


# ─── Structured Logger ─────────────────────────────────────────
class StructuredLogger:
    """Logger that always includes correlation_id and component name."""

    def __init__(self, component: str):
        self.component = component
        self._logger = logging.getLogger(f"coach.{component}")

    def _format(self, event: str, **kwargs) -> str:
        cid = correlation_id.get()
        parts = [f"[{cid}] [{self.component}] {event}"]
        for k, v in kwargs.items():
            if isinstance(v, str) and len(v) > 200:
                v = v[:200] + "..."
            parts.append(f"{k}={v}")
        return " | ".join(parts)

    def info(self, event: str, **kwargs):
        self._logger.info(self._format(event, **kwargs))

    def warning(self, event: str, **kwargs):
        self._logger.warning(self._format(event, **kwargs))

    def error(self, event: str, **kwargs):
        self._logger.error(self._format(event, **kwargs))

    def debug(self, event: str, **kwargs):
        self._logger.debug(self._format(event, **kwargs))


def get_logger(component: str) -> StructuredLogger:
    """Get a structured logger for a component."""
    return StructuredLogger(component)


# ─── Timing Decorator ──────────────────────────────────────────
def track_timing(component: str, operation: str):
    """Decorator that logs execution time of async functions."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_logger(component)
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                logger.info(
                    f"{operation}_complete",
                    duration_ms=round(elapsed * 1000),
                    status="success",
                )
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(
                    f"{operation}_failed",
                    duration_ms=round(elapsed * 1000),
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise
        return wrapper
    return decorator


# ─── Configure Logging ─────────────────────────────────────────
def configure_logging(debug: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
