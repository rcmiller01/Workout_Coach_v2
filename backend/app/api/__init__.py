from app.api.profile import router as profile_router
from app.api.planning import router as planning_router
from app.api.workouts import router as workouts_router
from app.api.meals import router as meals_router
from app.api.dashboard import router as dashboard_router
from app.api.admin import router as admin_router
from app.api.review import router as review_router

__all__ = [
    "profile_router",
    "planning_router",
    "workouts_router",
    "meals_router",
    "dashboard_router",
    "admin_router",
    "review_router",
]
