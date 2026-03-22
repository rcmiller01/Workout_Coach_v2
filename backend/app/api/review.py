"""
AI Fitness Coach v1 — Review API Routes

Weekly review and coach insights endpoints.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.review import WeeklyReviewService
from app.schemas.review import WeeklyReviewResponse, TrendsResponse

router = APIRouter(prefix="/api/review", tags=["Review"])
review_service = WeeklyReviewService()


@router.get("/weekly/{user_id}", response_model=WeeklyReviewResponse)
async def get_weekly_review(
    user_id: str,
    week_offset: int = Query(
        0,
        description="0 = current week, -1 = last week, etc.",
        ge=-52,
        le=0,
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated weekly analytics and insights.

    Returns:
    - Weight trend: start/end weights, change, trend direction, goal alignment
    - Workouts: planned vs completed, completion %, energy levels
    - Nutrition: adherence %, days on target, calorie averages
    - Coach adjustments: recent plan revisions and their impact
    - Insights: rule-based observations about progress
    - Next action: recommended next step

    Use week_offset to view previous weeks (e.g., -1 for last week).
    """
    return await review_service.generate_weekly_review(
        db=db,
        user_id=user_id,
        week_offset=week_offset,
    )


@router.get("/trends/{user_id}", response_model=TrendsResponse)
async def get_trends(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get 4-week trend analysis for weight, workouts, and nutrition.

    Returns:
    - **Trends**: 4-week direction for weight, workout completion, nutrition adherence
    - **Revision frequency**: How active the coach has been (stable/moderate/active)
    - **Goal alignment**: Overall status (on_track/mixed/off_track)

    Useful for dashboard summary cards and detecting if coach is over-adjusting.
    """
    return await review_service.generate_trends(
        db=db,
        user_id=user_id,
    )
