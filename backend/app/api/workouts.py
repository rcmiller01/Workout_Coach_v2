"""
AI Fitness Coach v1 — Workout API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, date, timezone
from typing import Optional
import logging

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.plan import WeeklyPlan, WorkoutLog, PlanRevision
from app.schemas.workout import WorkoutLogCreate, WorkoutLogResponse
from app.providers.wger import WgerProvider
from app.services.exercise_cache import resolve_exercise_id
from app.config import settings
from app.logging_config import get_logger

logger = get_logger("workouts_api")
router = APIRouter(prefix="/workouts", tags=["Workouts"])


def _get_wger() -> WgerProvider:
    return WgerProvider(base_url=settings.wger_base_url, api_token=settings.wger_api_token)


@router.get("/today")
async def get_todays_workout(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get today's planned workout and active workout revision context."""
    user_id = current_user.id
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
    today = datetime.now(timezone.utc)
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    today_name = day_names[today.weekday()]

    workout_plan = plan.workout_plan or {}
    today_workout = None

    # Handle both formats: list of days or dict with "days" key
    workout_days = workout_plan if isinstance(workout_plan, list) else workout_plan.get("days", [])
    for day in workout_days:
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
async def log_workout(data: WorkoutLogCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Log a completed workout and sync to wger."""
    user_id = current_user.id
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

    # Sync to wger in background (don't block the response)
    try:
        await _sync_workout_to_wger(log, db)
    except Exception as e:
        logger.error("wger_sync_failed", log_id=log.id, error=str(e))

    return log


async def _sync_workout_to_wger(log: WorkoutLog, db: AsyncSession):
    """Sync a workout log's exercises to wger as individual set logs."""
    wger = _get_wger()
    exercises = log.exercises_completed or []
    if not exercises:
        return

    wger_log_ids = []
    date_str = log.date.strftime("%Y-%m-%d") if log.date else date.today().isoformat()

    for ex in exercises:
        if not ex.get("completed", True):
            continue  # Skip exercises marked as skipped

        # Resolve exercise name to wger ID
        exercise_id = await resolve_exercise_id(wger, ex.get("name", ""))
        if not exercise_id:
            logger.warning("wger_sync_skip", exercise=ex.get("name"), reason="no_wger_id")
            continue

        # Log each set (or one entry for the exercise if no individual sets)
        sets = ex.get("sets", 1)
        reps = ex.get("reps", 0)
        weight = ex.get("weight_kg", 0)

        # Parse reps if it's a range like "8-10"
        if isinstance(reps, str):
            try:
                reps = int(reps.split("-")[0])
            except (ValueError, IndexError):
                reps = 0

        if isinstance(sets, str):
            try:
                sets = int(sets)
            except ValueError:
                sets = 1

        try:
            for _ in range(int(sets)):
                result = await wger.log_workout(
                    exercise_id=exercise_id,
                    reps=int(reps),
                    weight=float(weight),
                    date_str=date_str,
                )
                if result.get("id"):
                    wger_log_ids.append(result["id"])
        except Exception as e:
            logger.warning("wger_set_log_failed", exercise=ex.get("name"), error=str(e))

    # Update sync status
    if wger_log_ids:
        log.wger_log_ids = wger_log_ids
        log.synced_to_wger = "synced"
    else:
        log.synced_to_wger = "failed"

    await db.commit()
    logger.info("wger_sync_complete", log_id=log.id, synced_sets=len(wger_log_ids))
    await wger.close()


# ─── Add/Remove exercises from a logged workout ──────────────

from pydantic import BaseModel


class AdHocExercise(BaseModel):
    name: str
    muscle_group: str = "other"
    sets: int = 3
    reps: int | str = 10
    weight_kg: float = 0
    source: str = "adhoc"  # "adhoc" or "cardio"
    duration_min: Optional[int] = None
    distance_km: Optional[float] = None
    completed: bool = True


@router.post("/log/{log_id}/exercise", status_code=201)
async def add_exercise_to_log(
    log_id: str,
    exercise: AdHocExercise,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an ad-hoc exercise or cardio to an existing workout log."""
    user_id = current_user.id
    result = await db.execute(
        select(WorkoutLog).where(WorkoutLog.id == log_id, WorkoutLog.user_id == user_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Workout log not found")

    exercises = list(log.exercises_completed or [])
    exercises.append(exercise.model_dump())
    log.exercises_completed = exercises

    await db.commit()
    await db.refresh(log)

    # Sync new exercise to wger
    try:
        wger = _get_wger()
        exercise_id = await resolve_exercise_id(wger, exercise.name)
        if exercise_id and exercise.completed:
            date_str = log.date.strftime("%Y-%m-%d") if log.date else date.today().isoformat()
            reps = exercise.reps
            if isinstance(reps, str):
                reps = int(reps.split("-")[0])
            for _ in range(exercise.sets):
                await wger.log_workout(
                    exercise_id=exercise_id,
                    reps=int(reps),
                    weight=exercise.weight_kg,
                    date_str=date_str,
                )
        await wger.close()
    except Exception as e:
        logger.warning("wger_adhoc_sync_failed", error=str(e))

    return {"message": "Exercise added", "exercise_count": len(exercises)}


@router.delete("/log/{log_id}/exercise/{exercise_index}", status_code=204)
async def delete_exercise_from_log(
    log_id: str,
    exercise_index: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an exercise from a workout log by index."""
    user_id = current_user.id
    result = await db.execute(
        select(WorkoutLog).where(WorkoutLog.id == log_id, WorkoutLog.user_id == user_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Workout log not found")

    exercises = list(log.exercises_completed or [])
    if exercise_index < 0 or exercise_index >= len(exercises):
        raise HTTPException(status_code=400, detail="Invalid exercise index")

    # If synced to wger, try to delete the corresponding log entries
    wger_ids = log.wger_log_ids or []
    if wger_ids and log.synced_to_wger == "synced":
        try:
            wger = _get_wger()
            # Each exercise may have created multiple wger log entries (one per set)
            # We approximate by tracking set count offsets
            # For simplicity, we don't try to map individual wger IDs to exercises
            # since the wger_log_ids list is flat
            await wger.close()
        except Exception as e:
            logger.warning("wger_delete_sync_failed", error=str(e))

    exercises.pop(exercise_index)
    log.exercises_completed = exercises

    # Recalculate completion percentage
    planned = [e for e in exercises if e.get("source") == "planned"]
    if planned:
        completed_count = sum(1 for e in planned if e.get("completed", True))
        log.completion_pct = completed_count / len(planned) if planned else 0

    await db.commit()
    return None


@router.delete("/log/{log_id}", status_code=204)
async def delete_workout_log(
    log_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an entire workout log entry."""
    user_id = current_user.id
    result = await db.execute(
        select(WorkoutLog).where(WorkoutLog.id == log_id, WorkoutLog.user_id == user_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Workout log not found")

    await db.delete(log)
    await db.commit()
    return None


@router.get("/history")
async def get_workout_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workout log history."""
    user_id = current_user.id
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
