"""
AI Fitness Coach v1 — Review API Routes

Weekly review and coach insights endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services.review import WeeklyReviewService
from app.schemas.review import WeeklyReviewResponse, TrendsResponse

router = APIRouter(prefix="/api/review", tags=["Review"])
review_service = WeeklyReviewService()


@router.get("/weekly", response_model=WeeklyReviewResponse)
async def get_weekly_review(
    week_offset: int = Query(0, ge=-52, le=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated weekly analytics and insights."""
    user_id = current_user.id
    return await review_service.generate_weekly_review(
        db=db,
        user_id=user_id,
        week_offset=week_offset,
    )


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get 4-week trend analysis for weight, workouts, and nutrition."""
    user_id = current_user.id
    return await review_service.generate_trends(
        db=db,
        user_id=user_id,
    )
