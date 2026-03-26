"""
AI Fitness Coach v1 — Profile API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.api.deps import get_current_user
from app.logging_config import get_logger
from datetime import datetime, timedelta, timezone

logger = get_logger("profile_api")
from app.models.user import User, UserProfile, WeightEntry, DailySteps
from app.schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse
from app.schemas.plan import (
    WeightEntryRequest,
    WeightSyncRequest,
    WeightEntryResponse,
    LatestWeightResponse,
    WeightSyncResult,
)
from app.services.weight_sync import WeightSyncService

router = APIRouter(prefix="/profile", tags=["Profile"])
weight_sync_service = WeightSyncService()

@router.post("/", response_model=ProfileResponse, status_code=201)
async def create_profile(data: ProfileCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Create a new user profile."""
    data.user_id = current_user.id
    # Check if profile already exists for this user
    existing = await db.execute(
        select(UserProfile).where(UserProfile.user_id == data.user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Profile already exists for this user")

    # Ensure user exists (create if needed for dev convenience)
    user = await db.execute(select(User).where(User.id == data.user_id))
    if not user.scalar_one_or_none():
        new_user = User(id=data.user_id, username=f"user_{data.user_id[:8]}")
        db.add(new_user)

    profile = UserProfile(
        user_id=data.user_id,
        goal=data.goal,
        equipment=data.equipment,
        days_per_week=data.days_per_week,
        session_length_min=data.session_length_min,
        preferred_workout_time=data.preferred_workout_time,
        target_calories=data.target_calories,
        target_protein_g=data.target_protein_g,
        target_carbs_g=data.target_carbs_g,
        target_fat_g=data.target_fat_g,
        dietary_restrictions=data.dietary_restrictions,
        dietary_preferences=data.dietary_preferences,
        injuries=[inj.model_dump() for inj in data.injuries],
        health_conditions=data.health_conditions,
        height_cm=data.height_cm,
        weight_kg=data.weight_kg,
        age=data.age,
        sex=data.sex,
        body_fat_pct=data.body_fat_pct,
        activity_level=data.activity_level,
        coaching_persona=data.coaching_persona,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile

@router.get("/me", response_model=ProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get the authenticated user's profile."""
    user_id = current_user.id
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@router.put("/me", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's profile."""
    user_id = current_user.id
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = data.model_dump(exclude_unset=True)
    if "injuries" in update_data and update_data["injuries"] is not None:
        update_data["injuries"] = [
            inj.model_dump() if hasattr(inj, "model_dump") else inj
            for inj in update_data["injuries"]
        ]

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return profile

@router.delete("/me", status_code=204)
async def delete_profile(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete the authenticated user's profile."""
    user_id = current_user.id
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.delete(profile)
    await db.commit()

@router.post("/weight", status_code=201)
async def log_weight(data: WeightEntryRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Log manual body weight."""
    data.user_id = current_user.id
    entry = WeightEntry(
        user_id=data.user_id,
        weight_kg=data.weight_kg,
        source="manual",
        notes=data.notes
    )
    db.add(entry)

    # Update profile weight as well
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == data.user_id))
    profile = result.scalar_one_or_none()
    if profile:
        profile.weight_kg = data.weight_kg

    await db.commit()

    # Sync to wger (fire-and-forget, don't block the response)
    try:
        from app.providers.wger import WgerProvider
        from app.config import settings as app_settings
        wger = WgerProvider(base_url=app_settings.wger_base_url, api_token=app_settings.wger_api_token)
        await wger.log_weight(data.weight_kg)
        entry.synced_to_wger = "synced"
        await db.commit()
        await wger.close()
    except Exception as e:
        logger.warning("wger_weight_sync_failed", error=str(e))

    return {"status": "success", "weight": data.weight_kg, "source": "manual"}


@router.post("/weight/sync", response_model=WeightSyncResult, status_code=201)
async def sync_weight(data: WeightSyncRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Sync a weight entry from an external source (HealthKit, Google Fit, etc.).
    """
    data.user_id = current_user.id
    status, entry, replan_triggered, revision_id = await weight_sync_service.sync_weight(
        db=db,
        user_id=data.user_id,
        weight_kg=data.weight_kg,
        source=data.source,
        source_id=data.source_id,
        measured_at=data.measured_at,
        notes=data.notes,
    )

    # If replan was triggered, call the replan endpoint
    if replan_triggered:
        from app.api.planning import adaptive_replan
        try:
            revision = await adaptive_replan(data.user_id, db)
            revision_id = revision.id
        except HTTPException:
            # Plan might not exist or other issue
            replan_triggered = False
            revision_id = None

    await db.commit()

    message_map = {
        "created": f"Weight {data.weight_kg}kg synced from {data.source}",
        "deduplicated": f"Duplicate entry from {data.source} ignored",
        "updated": f"Weight entry updated from {data.source}",
    }

    return WeightSyncResult(
        status=status,
        weight_entry=WeightEntryResponse.model_validate(entry) if entry else None,
        replan_triggered=replan_triggered,
        revision_id=revision_id,
        message=message_map.get(status, "Weight synced"),
    )


@router.get("/weight/latest", response_model=LatestWeightResponse)
async def get_latest_weight(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get the latest weight entry with source metadata and trend info."""
    user_id = current_user.id
    result = await weight_sync_service.get_latest_weight(db, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="No weight entries found")

    return LatestWeightResponse(**result)

@router.get("/weight/history")
async def get_weight_history(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Retrieve weight history and plan revisions for progress tracking."""
    user_id = current_user.id
    # 1. Weight Entries
    res = await db.execute(
        select(WeightEntry).where(WeightEntry.user_id == user_id)
        .order_by(desc(WeightEntry.date))
    )
    weights = res.scalars().all()

    # 2. Plan Revisions (to overlay on chart)
    from app.models.plan import PlanRevision
    res = await db.execute(
        select(PlanRevision).where(PlanRevision.user_id == user_id)
        .order_by(desc(PlanRevision.created_at))
    )
    revisions = res.scalars().all()

    # 3. Get last sync time from any external source
    sync_res = await db.execute(
        select(WeightEntry.synced_at)
        .where(
            WeightEntry.user_id == user_id,
            WeightEntry.source != "manual",
            WeightEntry.synced_at.isnot(None),
        )
        .order_by(desc(WeightEntry.synced_at))
        .limit(1)
    )
    last_sync_time = sync_res.scalar_one_or_none()

    weight_entries = [
        {
            "id": w.id,
            "date": w.date.isoformat(),
            "weight_kg": w.weight_kg,
            "source": w.source,
            "source_id": w.source_id,
            "synced_at": w.synced_at.isoformat() if w.synced_at else None,
            "notes": w.notes
        } for w in weights
    ]

    return {
        "weight_entries": weight_entries,
        "entry_count": len(weight_entries),
        "revisions": [
            {
                "id": r.id,
                "date": r.created_at.isoformat(),
                "trigger": r.trigger,
                "reason": r.reason,
                "status": r.status,
                "patch": r.patch
            } for r in revisions
        ],
        "revision_count": len(revisions),
        "last_sync_time": last_sync_time.isoformat() if last_sync_time else None,
        "message": None if weight_entries else "No weight entries yet - log your first weight!",
    }


# ─── Steps Tracking ──────────────────────────────────────────

STEP_TIERS = [
    (5000,  "sedentary",    -100),
    (8000,  "light",           0),
    (12000, "moderate",      100),
    (99999, "very_active",   200),
]

def _steps_to_calorie_adjustment(steps: int) -> tuple[str, int]:
    """Convert step count to an activity tier and calorie adjustment."""
    for threshold, tier, adjustment in STEP_TIERS:
        if steps < threshold:
            return tier, adjustment
    return "very_active", 200


from pydantic import BaseModel
from typing import Optional

class StepsLogRequest(BaseModel):
    steps: int
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    source: str = "manual"


@router.post("/steps", status_code=201)
async def log_steps(data: StepsLogRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Log daily step count. Affects calorie/activity interpretation only."""
    user_id = current_user.id
    step_date = datetime.strptime(data.date, "%Y-%m-%d").replace(tzinfo=timezone.utc) if data.date else datetime.now(timezone.utc)

    # Upsert: replace existing entry for same user+date+source
    day_start = step_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    existing = await db.execute(
        select(DailySteps).where(
            DailySteps.user_id == user_id,
            DailySteps.date >= day_start,
            DailySteps.date < day_end,
            DailySteps.source == data.source,
        )
    )
    entry = existing.scalar_one_or_none()
    if entry:
        entry.steps = data.steps
    else:
        entry = DailySteps(user_id=user_id, date=step_date, steps=data.steps, source=data.source)
        db.add(entry)

    await db.commit()

    tier, cal_adjust = _steps_to_calorie_adjustment(data.steps)
    return {
        "status": "logged",
        "steps": data.steps,
        "date": step_date.strftime("%Y-%m-%d"),
        "activity_tier": tier,
        "calorie_adjustment": cal_adjust,
    }


@router.get("/steps/summary")
async def get_steps_summary(days: int = Query(7, ge=1, le=90), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get step count summary with calorie adjustment recommendation."""
    user_id = current_user.id
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(DailySteps).where(
            DailySteps.user_id == user_id,
            DailySteps.date >= cutoff,
        ).order_by(desc(DailySteps.date))
    )
    entries = result.scalars().all()

    if not entries:
        return {
            "entries": [],
            "average_steps": 0,
            "activity_tier": "unknown",
            "calorie_adjustment": 0,
            "days_tracked": 0,
            "message": "No step data yet. Log your daily steps to get activity-based calorie adjustments.",
        }

    avg_steps = sum(e.steps for e in entries) // len(entries)
    tier, cal_adjust = _steps_to_calorie_adjustment(avg_steps)

    return {
        "entries": [
            {
                "date": e.date.strftime("%Y-%m-%d"),
                "steps": e.steps,
                "source": e.source,
            }
            for e in entries
        ],
        "average_steps": avg_steps,
        "activity_tier": tier,
        "calorie_adjustment": cal_adjust,
        "days_tracked": len(entries),
    }

