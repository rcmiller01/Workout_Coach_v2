"""
AI Fitness Coach v1 — Main Application Entry Point

Orchestration API that sits between the frontend and
external systems (wger, Tandoor, LLM).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.config import settings
from app.database import init_db
from app.api import (
    profile_router,
    planning_router,
    workouts_router,
    meals_router,
    dashboard_router,
    admin_router,
    review_router,
)
import logging
import os
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
from app.config import settings
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

    # 2. Init Database
    await init_db()
    logger.info("database_initialized")

    # 3. Startup Health Checks (Hardening)
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
)

# ─── Middleware ────────────────────────────────────────────────

app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────

# API Routes
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(profile_router, prefix="/api", tags=["Profile"])
app.include_router(planning_router, prefix="/api", tags=["Planning"])
app.include_router(workouts_router, prefix="/api", tags=["Workouts"])
app.include_router(meals_router, prefix="/api", tags=["Meals"])
app.include_router(admin_router)  # Has its own /api/admin prefix
app.include_router(review_router)  # Has its own /api/review prefix

# Disable caching for static files in development
if settings.debug:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            if not request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response

    app.add_middleware(NoCacheMiddleware)

# Static Files (Frontend PWA)
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
