"""
AI Fitness Coach v1 — Dashboard API Route
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime
from app.database import get_db
from app.models.user import UserProfile
from app.models.plan import WeeklyPlan, WorkoutLog, AdherenceRecord, PlanRevision
from app.schemas.plan import DashboardResponse, PlanRevisionResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

PERSONA_GREETINGS = {
    "direct": ["Here's your plan for today.", "Let's get to work.", "Today's lineup is ready."],
    "supportive": [
        "Great to see you! Here's what we've got today. 💪",
        "You're doing amazing — let's keep the momentum going!",
        "Another day, another opportunity to crush it!",
    ],
    "technical": [
        "Today's training stimulus is programmed below.",
        "Here's your periodized plan for today.",
        "Today targets key muscle groups per your mesocycle.",
    ],
    "quiet": ["Today's plan:", ""],
}

@router.get("/dashboard/{user_id}", response_model=DashboardResponse)
async def get_dashboard(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the today-view dashboard — the primary screen of the app.
    Combines: today's workout + meals + progress snapshot + coaching message + plan revisions.
    """
    today = datetime.now()
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    today_name = day_names[today.weekday()]
    today_str = today.strftime("%Y-%m-%d")

    # 1. Load profile
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()
    persona = profile.coaching_persona if profile else "supportive"

    # 2. Get greeting
    import random
    greetings = PERSONA_GREETINGS.get(persona, PERSONA_GREETINGS["supportive"])
    greeting = random.choice(greetings)

    # 3. Load active plan
    plan_result = await db.execute(
        select(WeeklyPlan)
        .where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
        .order_by(desc(WeeklyPlan.created_at))
        .limit(1)
    )
    plan = plan_result.scalar_one_or_none()

    today_workout = None
    today_meals = []
    macro_targets = {}
    shopping_list_count = 0
    next_workout = None
    revisions = []

    if plan:
        workout_plan = plan.workout_plan or {}
        meal_plan = plan.meal_plan or {}

        # Find today's workout
        for day in workout_plan.get("days", []):
            if day.get("day", "").lower() == today_name.lower():
                today_workout = day
                break

        # Find today's meals
        for day in meal_plan.get("days", []):
            if day.get("day", "").lower() == today_name.lower():
                today_meals = day.get("meals", [])
                macro_targets = day.get("totals", {})
                break

        # Count shopping list items
        shopping_list_count = len(plan.shopping_list or [])

        # Find next workout
        today_idx = today.weekday()
        for i in range(1, 7):
            next_day_idx = (today_idx + i) % 7
            next_day_name = day_names[next_day_idx]
            for day in workout_plan.get("days", []):
                if day.get("day", "").lower() == next_day_name.lower() and not day.get("is_rest_day"):
                    next_workout = {"day": next_day_name, "focus": day.get("focus", "")}
                    break
            if next_workout: break

        # Fetch recent revisions
        rev_result = await db.execute(
            select(PlanRevision).where(PlanRevision.plan_id == plan.id)
            .order_by(desc(PlanRevision.created_at)).limit(3)
        )
        revisions = rev_result.scalars().all()

    # 4. Check workout completion
    workout_completed = False
    if plan:
        log_result = await db.execute(
            select(WorkoutLog).where(WorkoutLog.user_id == user_id, WorkoutLog.plan_id == plan.id)
        )
        logs = log_result.scalars().all()
        workout_completed = any(l.date.strftime("%Y-%m-%d") == today_str if l.date else False for l in logs)

    # 5. Weekly adherence
    weekly_adherence = None
    if plan:
        log_result = await db.execute(select(WorkoutLog).where(WorkoutLog.user_id == user_id).limit(10))
        recent_logs = log_result.scalars().all()
        if recent_logs:
            training_days = len([d for d in (plan.workout_plan or {}).get("days", []) if not d.get("is_rest_day")])
            if training_days > 0:
                weekly_adherence = min(1.0, len(recent_logs) / training_days) * 100

    # Determine coaching message for empty states
    coaching_message = None
    if not profile:
        coaching_message = "Welcome! Complete your profile to get started with personalized training."
    elif not plan:
        coaching_message = "Your profile is set up! Generate your first weekly plan to begin."
    elif today_workout and today_workout.get("is_rest_day"):
        coaching_message = "Today is a rest day. Recovery is just as important as training!"

    return DashboardResponse(
        date=today_str,
        greeting=greeting,
        coaching_message=coaching_message,
        workout=today_workout,
        workout_completed=workout_completed,
        meals=today_meals,
        macro_targets=macro_targets,
        macro_actuals=None,
        current_weight_kg=profile.weight_kg if profile else None,
        weight_trend=None,
        weekly_adherence_pct=weekly_adherence,
        next_workout=next_workout,
        shopping_list_count=shopping_list_count,
        revisions=[PlanRevisionResponse.from_orm(r) for r in revisions]
    )

@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "AI Fitness Coach v1", "timestamp": datetime.now().isoformat()}
