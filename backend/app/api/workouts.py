"""
AI Fitness Coach v1 — Workout API Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, date
from app.database import get_db
from app.models.plan import WeeklyPlan, WorkoutLog, PlanRevision
from app.schemas.workout import WorkoutLogCreate, WorkoutLogResponse

router = APIRouter(prefix="/workouts", tags=["Workouts"])


@router.get("/today/{user_id}")
async def get_todays_workout(user_id: str, db: AsyncSession = Depends(get_db)):
    """Get today's planned workout and active workout revision context."""
    # Find active plan
    result = await db.execute(
        select(WeeklyPlan)
        .where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
        .order_by(desc(WeeklyPlan.created_at))
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return {
            "message": "No active plan - generate one to get started!",
            "workout": None,
            "completed": False,
            "is_rest_day": False,
            "plan_id": None,
            "impact_summary": None,
        }

    # Find today's workout
    today = datetime.now()
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    today_name = day_names[today.weekday()]

    workout_plan = plan.workout_plan or {}
    today_workout = None

    for day in workout_plan.get("days", []):
        if day.get("day", "").lower() == today_name.lower():
            today_workout = day
            break

    # Check if already completed today
    log_result = await db.execute(
        select(WorkoutLog)
        .where(
            WorkoutLog.user_id == user_id,
            WorkoutLog.plan_id == plan.id,
        )
    )
    logs = log_result.scalars().all()
    today_str = today.strftime("%Y-%m-%d")
    completed = any(
        l.date.strftime("%Y-%m-%d") == today_str if l.date else False
        for l in logs
    )

    # Get workout revisions for impact summary
    rev_result = await db.execute(
        select(PlanRevision)
        .where(
            PlanRevision.plan_id == plan.id,
            PlanRevision.target_area.in_(["workout", "both"])
        )
        .order_by(desc(PlanRevision.created_at))
    )
    db_revisions = rev_result.scalars().all()

    # Build revision impact summary for active adjustments
    active_adjustments = []
    effective_rev = next((r for r in db_revisions if r.status in ("applied", "approved", "pending")), None)

    if effective_rev:
        vol_modifier = effective_rev.patch.get("workout_plan", {}).get("global_modifier", 0)
        if vol_modifier != 0:
            pct = int(vol_modifier * 100)
            sign = "+" if pct > 0 else ""
            active_adjustments.append(f"volume {sign}{pct}%")

    # Build impact summary string
    impact_summary = None
    if active_adjustments:
        impact_summary = f"This week's active adjustments: {', '.join(active_adjustments)}"

    # Determine if today is a rest day
    is_rest_day = today_workout.get("is_rest_day", False) if today_workout else False

    # Set appropriate message for rest days or completion
    message = None
    if is_rest_day:
        message = "Rest day - recovery is key to progress!"
    elif completed:
        message = "Great job completing today's workout!"

    return {
        "date": today_str,
        "day": today_name,
        "workout": today_workout,
        "completed": completed,
        "is_rest_day": is_rest_day,
        "plan_id": plan.id,
        "impact_summary": impact_summary,
        "message": message,
    }


@router.post("/log", response_model=WorkoutLogResponse, status_code=201)
async def log_workout(data: WorkoutLogCreate, user_id: str, db: AsyncSession = Depends(get_db)):
    """Log a completed workout."""
    log = WorkoutLog(
        user_id=user_id,
        plan_id=data.plan_id,
        date=data.date,
        exercises_completed=data.exercises_completed,
        completion_pct=data.completion_pct,
        duration_min=data.duration_min,
        energy_level=data.energy_level,
        notes=data.notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.get("/history/{user_id}")
async def get_workout_history(
    user_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get workout log history."""
    result = await db.execute(
        select(WorkoutLog)
        .where(WorkoutLog.user_id == user_id)
        .order_by(desc(WorkoutLog.date))
        .limit(limit)
    )
    logs = result.scalars().all()

    entries = [
        {
            "id": l.id,
            "date": l.date.isoformat() if l.date else None,
            "exercises_completed": l.exercises_completed,
            "completion_pct": l.completion_pct,
            "duration_min": l.duration_min,
            "energy_level": l.energy_level,
            "synced_to_wger": l.synced_to_wger,
        }
        for l in logs
    ]

    return {
        "entries": entries,
        "count": len(entries),
        "message": None if entries else "No workout history yet - complete your first workout!",
    }
