"""
AI Fitness Coach v1 — Profile API Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.models.user import User, UserProfile, WeightEntry
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
async def create_profile(data: ProfileCreate, db: AsyncSession = Depends(get_db)):
    """Create a new user profile."""
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

@router.get("/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: str, db: AsyncSession = Depends(get_db)):
    """Get a user's profile."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@router.put("/{user_id}", response_model=ProfileResponse)
async def update_profile(
    user_id: str,
    data: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a user's profile."""
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

@router.delete("/{user_id}", status_code=204)
async def delete_profile(user_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a user's profile."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.delete(profile)
    await db.commit()

@router.post("/weight", status_code=201)
async def log_weight(data: WeightEntryRequest, db: AsyncSession = Depends(get_db)):
    """Log manual body weight."""
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
    except Exception:
        pass  # Don't fail weight logging if wger sync fails

    return {"status": "success", "weight": data.weight_kg, "source": "manual"}


@router.post("/weight/sync", response_model=WeightSyncResult, status_code=201)
async def sync_weight(data: WeightSyncRequest, db: AsyncSession = Depends(get_db)):
    """
    Sync a weight entry from an external source (HealthKit, Google Fit, etc.).

    This endpoint:
    - Deduplicates near-identical entries from the same source
    - Routes synced weights through normal trend evaluation
    - May trigger a replan if thresholds are met (respecting cooldown)
    - Never directly mutates the plan from raw sync input

    Returns sync status and whether a replan was triggered.
    """
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


@router.get("/weight/latest/{user_id}", response_model=LatestWeightResponse)
async def get_latest_weight(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the latest weight entry with source metadata and trend info.

    Returns:
    - weight_kg, date, source
    - last_sync_time: most recent sync from any external source
    - trend: up | down | stable
    - delta_kg: change from previous entry
    """
    result = await weight_sync_service.get_latest_weight(db, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="No weight entries found")

    return LatestWeightResponse(**result)

@router.get("/weight/history/{user_id}")
async def get_weight_history(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve weight history and plan revisions for progress tracking.

    Weight entries include source metadata (manual, healthkit, google_fit, import).
    """
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

