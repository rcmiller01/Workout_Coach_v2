"""
AI Fitness Coach v1 — Main Application Entry Point

Orchestration API that sits between the frontend and
external systems (wger, Tandoor, LLM).
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.database import init_db
from app.rate_limit import limiter
from app.api import (
    profile_router,
    planning_router,
    workouts_router,
    meals_router,
    dashboard_router,
    admin_router,
    review_router,
)
from app.api.auth import router as auth_router
import logging
import os
import warnings
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
from app.logging_config import configure_logging, get_logger, CorrelationIdMiddleware
from app.providers.wger import WgerProvider
from app.providers.tandoor import TandoorProvider


# ─── Initialization ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for database and services."""
    # 1. Setup Logging
    configure_logging(debug=settings.debug)
    logger = get_logger("startup")
    logger.info("app_starting", name=settings.app_name, env=settings.app_env)

    # 2. Security checks
    if settings.is_production:
        if settings.secret_key in ("change-me-to-a-random-secret-key", "coach-dev-secret-key-change-in-production"):
            logger.critical("INSECURE_SECRET_KEY — set SECRET_KEY to a random value in production!")
            raise SystemExit("Refusing to start: SECRET_KEY is not set for production")
        if settings.cors_origins == "*":
            logger.warning("CORS allows all origins — set CORS_ORIGINS to your domain in production")
    elif settings.secret_key in ("change-me-to-a-random-secret-key",):
        logger.warning("Using default SECRET_KEY — acceptable for development only")

    # 3. Init Database
    await init_db()
    logger.info("database_initialized")

    # 4. Startup Health Checks
    await run_startup_checks(logger)

    yield
    logger.info("app_shutting_down")


async def run_startup_checks(logger):
    """Validate external service connectivity on boot."""
    # wger Check
    wger = WgerProvider(settings.wger_base_url, settings.wger_api_token)
    if await wger.health_check():
        logger.info("provider_status", provider="wger", status="connected")
    else:
        logger.warning("provider_status", provider="wger", status="unreachable", msg="Check WGER_BASE_URL and token")
    await wger.close()

    # Ollama Check
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{settings.llm_base_url}/api/tags", timeout=2.0)
            if r.status_code == 200:
                logger.info("provider_status", provider="ollama", status="connected", model=settings.llm_model)
            else:
                logger.warning("provider_status", provider="ollama", status="error", code=r.status_code)
    except Exception as e:
        logger.warning("provider_status", provider="ollama", status="unreachable", error=str(e))


app = FastAPI(
    title=settings.app_name,
    description="AI-powered fitness orchestration API",
    version="1.0.0",
    lifespan=lifespan,
    # Disable docs in production
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# ─── Rate Limiter Setup ───────────────────────────────────────

app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )

# ─── Middleware ────────────────────────────────────────────────

app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Dev: disable caching for static files
        if settings.debug and not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ─── Routes ───────────────────────────────────────────────────

# API Routes
app.include_router(auth_router, prefix="/api", tags=["Auth"])
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(profile_router, prefix="/api", tags=["Profile"])
app.include_router(planning_router, prefix="/api", tags=["Planning"])
app.include_router(workouts_router, prefix="/api", tags=["Workouts"])
app.include_router(meals_router, prefix="/api", tags=["Meals"])
app.include_router(admin_router)  # Has its own /api/admin prefix
app.include_router(review_router)  # Has its own /api/review prefix

# Static Files (Frontend PWA)
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
