"""
AI Fitness Coach v1 — Admin API Routes

Administrative endpoints for development, testing, and operations.
These endpoints should be protected in production.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, timezone
import json

from app.database import get_db
from app.services.seed_data import SeedDataService, DEMO_USER_ID
from app.services.import_service import ImportService
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision, WorkoutLog, AdherenceRecord
from app.schemas.admin import (
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportRestoreRequest,
    ImportRestoreResponse,
    RestoreMode,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])
seed_service = SeedDataService()
import_service = ImportService()


class SeedResponse(BaseModel):
    """Response from seed operation."""
    success: bool
    user_id: str
    created: dict
    skipped: dict
    message: str


class DemoUserSummary(BaseModel):
    """Summary of demo user data."""
    user_id: str
    has_profile: bool
    profile_goal: Optional[str]
    weight_entries: int
    has_active_plan: bool
    plan_id: Optional[str]
    revision_count: int


@router.post("/seed/demo", response_model=SeedResponse, status_code=201)
async def seed_demo_data(
    clear_existing: bool = Query(
        False,
        description="If true, delete existing demo data before seeding"
    ),
    user_id: str = Query(
        DEMO_USER_ID,
        description="User ID to use for demo data"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Seed demo data for development and testing.

    Creates:
    - Demo user account
    - Full user profile with sensitivity settings
    - 14 days of weight history
    - Active weekly plan with 4-day upper/lower split
    - Sample meal plans
    - Sample plan revisions (superseded, applied, reverted)

    Idempotent by default - calling multiple times won't duplicate data.
    Use clear_existing=true to reset all demo data.
    """
    try:
        summary = await seed_service.seed_demo_user(
            db=db,
            user_id=user_id,
            clear_existing=clear_existing,
        )

        created_count = len([k for k, v in summary["created"].items() if v])
        skipped_count = len(summary["skipped"])

        if created_count > 0:
            message = f"Created {created_count} entities for demo user"
        elif skipped_count > 0:
            message = "Demo data already exists (use clear_existing=true to reset)"
        else:
            message = "Demo data seeded"

        return SeedResponse(
            success=True,
            user_id=summary["user_id"],
            created=summary["created"],
            skipped=summary["skipped"],
            message=message,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seed operation failed: {str(e)}")


@router.get("/seed/demo/status", response_model=DemoUserSummary)
async def get_demo_status(
    user_id: str = Query(DEMO_USER_ID, description="User ID to check"),
    db: AsyncSession = Depends(get_db),
):
    """
    Check the status of demo data.

    Returns a summary of what demo data exists for the specified user.
    """
    summary = await seed_service.get_demo_user_summary(db, user_id)
    return DemoUserSummary(**summary)


@router.delete("/seed/demo", status_code=204)
async def clear_demo_data(
    user_id: str = Query(DEMO_USER_ID, description="User ID to clear"),
    db: AsyncSession = Depends(get_db),
):
    """
    Clear all demo data for a user.

    Removes all associated data including:
    - User account
    - Profile
    - Weight entries
    - Plans and revisions
    - Workout logs and adherence records
    """
    await seed_service._clear_user_data(db, user_id)
    await db.commit()


# --- Audit Bundle Export ---


class AuditBundleMetadata(BaseModel):
    """Metadata for the audit bundle."""
    user_id: str
    exported_at: str
    version: str = "1.0"
    record_counts: dict


def _serialize_datetime(obj: Any) -> Any:
    """Recursively serialize datetime objects in a dict/list."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _serialize_datetime(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_datetime(item) for item in obj]
    return obj


@router.get("/export/{user_id}")
async def export_audit_bundle(
    user_id: str,
    include_plans: bool = Query(True, description="Include plan history"),
    include_revisions: bool = Query(True, description="Include revision history"),
    include_workout_logs: bool = Query(True, description="Include workout logs"),
    db: AsyncSession = Depends(get_db),
):
    """
    Export a complete audit bundle for a user.

    Returns a JSON bundle containing:
    - User profile and settings
    - Weight history with source metadata
    - Plan history (all plans, not just active)
    - Plan revisions (full audit trail)
    - Workout logs
    - Adherence records

    Useful for:
    - Debugging user issues
    - GDPR data export compliance
    - Data portability
    - Backup before destructive operations
    """
    bundle: dict[str, Any] = {
        "metadata": {},
        "user": None,
        "profile": None,
        "weight_entries": [],
        "plans": [],
        "revisions": [],
        "workout_logs": [],
        "adherence_records": [],
    }

    record_counts = {}

    # 1. User
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        bundle["user"] = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
        record_counts["user"] = 1
    else:
        record_counts["user"] = 0

    # 2. Profile
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        bundle["profile"] = {
            "user_id": profile.user_id,
            "goal": profile.goal,
            "equipment": profile.equipment,
            "days_per_week": profile.days_per_week,
            "session_length_min": profile.session_length_min,
            "preferred_workout_time": profile.preferred_workout_time,
            "target_calories": profile.target_calories,
            "target_protein_g": profile.target_protein_g,
            "target_carbs_g": profile.target_carbs_g,
            "target_fat_g": profile.target_fat_g,
            "dietary_restrictions": profile.dietary_restrictions,
            "dietary_preferences": profile.dietary_preferences,
            "injuries": profile.injuries,
            "health_conditions": profile.health_conditions,
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "age": profile.age,
            "sex": profile.sex,
            "body_fat_pct": profile.body_fat_pct,
            "activity_level": profile.activity_level,
            "coaching_persona": profile.coaching_persona,
            "replan_weight_threshold_kg": profile.replan_weight_threshold_kg,
            "replan_missed_workout_threshold": profile.replan_missed_workout_threshold,
            "replan_cooldown_days": profile.replan_cooldown_days,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
        record_counts["profile"] = 1
    else:
        record_counts["profile"] = 0

    # 3. Weight Entries
    weight_result = await db.execute(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id)
        .order_by(desc(WeightEntry.date))
    )
    weights = weight_result.scalars().all()
    bundle["weight_entries"] = [
        {
            "id": w.id,
            "user_id": w.user_id,
            "weight_kg": w.weight_kg,
            "date": w.date,
            "source": w.source,
            "source_id": w.source_id,
            "synced_at": w.synced_at,
            "notes": w.notes,
            "created_at": w.created_at,
        }
        for w in weights
    ]
    record_counts["weight_entries"] = len(weights)

    # 4. Plans
    if include_plans:
        plans_result = await db.execute(
            select(WeeklyPlan)
            .where(WeeklyPlan.user_id == user_id)
            .order_by(desc(WeeklyPlan.created_at))
        )
        plans = plans_result.scalars().all()
        bundle["plans"] = [
            {
                "id": p.id,
                "user_id": p.user_id,
                "week_start": p.week_start,
                "week_end": p.week_end,
                "status": p.status,
                "workout_plan": p.workout_plan,
                "meal_plan": p.meal_plan,
                "shopping_list": p.shopping_list,
                "llm_reasoning": p.llm_reasoning,
                "rules_applied": p.rules_applied,
                "created_at": p.created_at,
            }
            for p in plans
        ]
        record_counts["plans"] = len(plans)

    # 5. Revisions
    if include_revisions:
        rev_result = await db.execute(
            select(PlanRevision)
            .where(PlanRevision.user_id == user_id)
            .order_by(desc(PlanRevision.created_at))
        )
        revisions = rev_result.scalars().all()
        bundle["revisions"] = [
            {
                "id": r.id,
                "plan_id": r.plan_id,
                "user_id": r.user_id,
                "revision_number": r.revision_number,
                "trigger": r.trigger,
                "target_area": r.target_area,
                "reason": r.reason,
                "patch": r.patch,
                "status": r.status,
                "status_reason": r.status_reason,
                "is_auto_applied": r.is_auto_applied,
                "parent_revision_id": r.parent_revision_id,
                "superseded_by_id": r.superseded_by_id,
                "undone_at": r.undone_at,
                "undone_by_id": r.undone_by_id,
                "created_at": r.created_at,
            }
            for r in revisions
        ]
        record_counts["revisions"] = len(revisions)

    # 6. Workout Logs
    if include_workout_logs:
        logs_result = await db.execute(
            select(WorkoutLog)
            .where(WorkoutLog.user_id == user_id)
            .order_by(desc(WorkoutLog.date))
        )
        logs = logs_result.scalars().all()
        bundle["workout_logs"] = [
            {
                "id": log.id,
                "user_id": log.user_id,
                "plan_id": log.plan_id,
                "date": log.date,
                "exercises_completed": log.exercises_completed,
                "completion_pct": log.completion_pct,
                "duration_min": log.duration_min,
                "energy_level": log.energy_level,
                "notes": log.notes,
                "synced_to_wger": log.synced_to_wger,
                "created_at": log.created_at,
            }
            for log in logs
        ]
        record_counts["workout_logs"] = len(logs)

    # 7. Adherence Records
    adherence_result = await db.execute(
        select(AdherenceRecord)
        .where(AdherenceRecord.user_id == user_id)
        .order_by(desc(AdherenceRecord.date))
    )
    adherence = adherence_result.scalars().all()
    bundle["adherence_records"] = [
        {
            "id": a.id,
            "user_id": a.user_id,
            "plan_id": a.plan_id,
            "date": a.date,
            "workout_completed": a.workout_completed,
            "meals_logged": a.meals_logged,
            "notes": a.notes,
            "created_at": a.created_at,
        }
        for a in adherence
    ]
    record_counts["adherence_records"] = len(adherence)

    # Set metadata
    bundle["metadata"] = {
        "user_id": user_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
        "record_counts": record_counts,
    }

    # Serialize all datetime objects
    bundle = _serialize_datetime(bundle)

    # Return with appropriate headers for download
    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": f'attachment; filename="audit-bundle-{user_id}.json"'
        },
    )


@router.get("/export/{user_id}/summary")
async def get_export_summary(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a summary of what would be exported for a user.

    Useful for checking data existence before export.
    """
    from sqlalchemy import func

    counts = {}

    # User exists?
    user_result = await db.execute(select(User).where(User.id == user_id))
    counts["user_exists"] = user_result.scalar_one_or_none() is not None

    # Profile exists?
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    counts["profile_exists"] = profile_result.scalar_one_or_none() is not None

    # Weight entries
    weight_count = await db.execute(
        select(func.count()).select_from(WeightEntry).where(
            WeightEntry.user_id == user_id
        )
    )
    counts["weight_entries"] = weight_count.scalar() or 0

    # Plans
    plan_count = await db.execute(
        select(func.count()).select_from(WeeklyPlan).where(
            WeeklyPlan.user_id == user_id
        )
    )
    counts["plans"] = plan_count.scalar() or 0

    # Revisions
    rev_count = await db.execute(
        select(func.count()).select_from(PlanRevision).where(
            PlanRevision.user_id == user_id
        )
    )
    counts["revisions"] = rev_count.scalar() or 0

    # Workout logs
    log_count = await db.execute(
        select(func.count()).select_from(WorkoutLog).where(
            WorkoutLog.user_id == user_id
        )
    )
    counts["workout_logs"] = log_count.scalar() or 0

    # Adherence
    adherence_count = await db.execute(
        select(func.count()).select_from(AdherenceRecord).where(
            AdherenceRecord.user_id == user_id
        )
    )
    counts["adherence_records"] = adherence_count.scalar() or 0

    total = sum(v for k, v in counts.items() if isinstance(v, int))

    return {
        "user_id": user_id,
        "counts": counts,
        "total_records": total,
        "has_data": total > 0 or counts["user_exists"] or counts["profile_exists"],
    }


# --- Import / Restore ---


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    request: ImportPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Preview what will be restored from an audit bundle.

    Returns:
    - **valid**: Whether the bundle passes validation
    - **preview**: What will be created/updated/skipped
    - **conflicts**: Potential conflicts in merge mode
    - **warnings**: Non-blocking issues to be aware of

    Use this before calling /import/restore to understand the impact.
    """
    return await import_service.preview_restore(
        db=db,
        bundle=request.bundle,
        target_user_id=request.target_user_id,
    )


@router.post("/import/restore", response_model=ImportRestoreResponse)
async def restore_from_bundle(
    request: ImportRestoreRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Restore user data from an audit bundle.

    **Modes**:
    - `replace`: Delete all existing data for the user, then restore from bundle.
      Creates a backup before deletion.
    - `merge`: Add new records only, skip existing ones. Never deletes.

    **Options**:
    - `dry_run`: Validate and preview without committing changes
    - `target_user_id`: Restore to a different user ID than the source

    **Safety**:
    - Replace mode always creates a backup first (see backup_id in response)
    - Dry-run mode lets you test without risk
    - Call /import/preview first to understand impact
    """
    return await import_service.execute_restore(
        db=db,
        bundle=request.bundle,
        mode=request.mode,
        dry_run=request.dry_run,
        target_user_id=request.target_user_id,
    )
