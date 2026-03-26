"""
AI Fitness Coach v1 — Planning API Routes

Revision state handling:
    - pending:    proposed but not yet applied (needs user approval)
    - applied:    auto-applied without user interaction
    - approved:   user explicitly approved a pending revision
    - reverted:   user undid this revision via compensating patch
    - superseded: newer revision targeting the same area replaced this one
    - blocked:    could not be applied due to a newer plan revision
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.rate_limit import limiter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update, and_, or_
from datetime import datetime, timedelta, timezone
import json
import logging

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision
from app.schemas.plan import WeeklyPlanRequest, WeeklyPlanResponse, PlanRevisionResponse
from app.providers.wger import WgerProvider
from app.providers.tandoor import TandoorProvider
from app.services.planning import PlanningService
from app.config import settings
from app.logging_config import get_logger

logger = get_logger("planning_api")
router = APIRouter(prefix="/planning", tags=["Planning"])

# --- Valid revision states ---
ACTIVE_STATES = {"pending", "applied", "approved"}
TERMINAL_STATES = {"reverted", "superseded", "blocked"}

def _get_planning_service():
    wger = WgerProvider(base_url=settings.wger_base_url, api_token=settings.wger_api_token)
    tandoor = TandoorProvider(base_url=settings.tandoor_base_url, api_token=settings.tandoor_api_token)
    return PlanningService(wger, tandoor)


def _infer_target_area(trigger: str, patch: dict) -> str:
    """Determine whether a revision targets workout, nutrition, or both."""
    has_workout = bool(patch.get("workout_plan", {}))
    has_nutrition = bool(patch.get("meal_plan", {}))

    if trigger in ("missed_workout", "volume_adjust"):
        return "workout"
    if trigger in ("calorie_adjust", "meal_non_adherence"):
        return "nutrition"
    if has_workout and not has_nutrition:
        return "workout"
    if has_nutrition and not has_workout:
        return "nutrition"
    return "both"


async def _supersede_active_revisions(
    db: AsyncSession,
    plan_id: str,
    target_area: str,
    new_revision_id: str,
    trigger: str,
) -> int:
    """
    Supersede any active (pending/applied) revisions for the same plan area.
    Returns the count of superseded revisions.

    Rules:
    - A new revision that touches the same target supersedes the older one
    - Only one active auto-adjustment chain per plan area at a time
    """
    # Find active revisions targeting the same area (or 'both')
    area_filter = or_(
        PlanRevision.target_area == target_area,
        PlanRevision.target_area == "both",
    )
    if target_area == "both":
        area_filter = True  # Supersede everything active

    result = await db.execute(
        select(PlanRevision).where(
            and_(
                PlanRevision.plan_id == plan_id,
                PlanRevision.id != new_revision_id,
                PlanRevision.status.in_(["pending", "applied"]),
                area_filter,
            )
        )
    )
    active_revisions = result.scalars().all()

    trigger_label = trigger.replace("_", " ")
    for rev in active_revisions:
        rev.status = "superseded"
        rev.superseded_by_id = new_revision_id
        rev.status_reason = f"Superseded by newer {trigger_label}"

    return len(active_revisions)


async def _get_next_revision_number(db: AsyncSession, plan_id: str) -> int:
    """Get the next revision number for a plan."""
    result = await db.execute(
        select(func.max(PlanRevision.revision_number)).where(
            PlanRevision.plan_id == plan_id
        )
    )
    max_num = result.scalar_one_or_none()
    return (max_num or 0) + 1


@router.post("/weekly", response_model=WeeklyPlanResponse, status_code=201)
@limiter.limit("3/hour")
async def generate_weekly_plan(request: Request, plan_data: WeeklyPlanRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    plan_data.user_id = current_user.id
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == plan_data.user_id))
    profile_model = result.scalar_one_or_none()
    if not profile_model:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile_dict = {
        "user_id": profile_model.user_id,
        "goal": profile_model.goal,
        "equipment": profile_model.equipment or [],
        "days_per_week": profile_model.days_per_week,
        "session_length_min": profile_model.session_length_min,
        "preferred_workout_time": profile_model.preferred_workout_time,
        "injuries": profile_model.injuries or [],
        "workout_notes": profile_model.workout_notes or "",
        "target_calories": profile_model.target_calories,
        "target_protein_g": profile_model.target_protein_g,
        "dietary_restrictions": profile_model.dietary_restrictions or [],
        "dietary_preferences": profile_model.dietary_preferences or [],
    }

    service = _get_planning_service()
    try:
        norm_plan = await service.create_weekly_plan(profile=profile_dict, fast_mode=plan_data.fast_mode)
    except Exception as e:
        logger.error("api_planning_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate plan")

    # Replace old plans BEFORE adding the new one to avoid self-replacement
    from sqlalchemy import update as sql_update
    old_plans_result = await db.execute(
        select(WeeklyPlan).where(
            WeeklyPlan.user_id == plan_data.user_id,
            WeeklyPlan.status == "active",
        )
    )
    old_plans = old_plans_result.scalars().all()
    for old_plan in old_plans:
        old_plan.status = "replaced"
        # Block any pending/applied revisions on the old plan
        await db.execute(
            sql_update(PlanRevision).where(
                PlanRevision.plan_id == old_plan.id,
                PlanRevision.status.in_(["pending", "applied"])
            ).values(
                status="blocked",
                status_reason="Blocked due to newer plan revision"
            )
        )

    new_plan = WeeklyPlan(
        user_id=plan_data.user_id,
        week_start=datetime.strptime(norm_plan.week_start, "%Y-%m-%d").replace(tzinfo=timezone.utc),
        week_end=datetime.strptime(norm_plan.week_end, "%Y-%m-%d").replace(tzinfo=timezone.utc),
        status="active",
        workout_plan=[d.model_dump() for d in norm_plan.workout_plan],
        meal_plan=[d.model_dump() for d in norm_plan.meal_plan],
        shopping_list=[],
        llm_reasoning=json.dumps({"metadata": norm_plan.metadata}),
        rules_applied=norm_plan.rules_applied
    )
    db.add(new_plan)

    await db.commit()
    await db.refresh(new_plan)
    return new_plan


@router.get("/current", response_model=WeeklyPlanResponse)
async def get_current_plan(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = current_user.id
    res = await db.execute(select(WeeklyPlan).where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active").order_by(desc(WeeklyPlan.created_at)).limit(1))
    plan = res.scalar_one_or_none()
    if not plan: raise HTTPException(status_code=404, detail="No active plan found")
    return plan


@router.post("/replan", response_model=PlanRevisionResponse)
@limiter.limit("10/hour")
async def adaptive_replan(request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = current_user.id
    # 1. Get Active Plan
    res = await db.execute(select(WeeklyPlan).where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active").order_by(desc(WeeklyPlan.created_at)))
    plan = res.scalar_one_or_none()
    if not plan: raise HTTPException(status_code=404, detail="No active plan")

    # 2. Extract context
    res = await db.execute(select(WeightEntry).where(WeightEntry.user_id == user_id).order_by(desc(WeightEntry.date)).limit(2))
    weights = res.scalars().all()
    weight_delta = weights[0].weight_kg - weights[1].weight_kg if len(weights) >= 2 else 0.0

    res = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = res.scalar_one_or_none()

    adherence_summary = {"missed_workouts": 0, "meal_adherence_pct": 100}

    # 2b. Steps-based calorie adjustment
    from app.models.user import DailySteps
    steps_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    steps_res = await db.execute(
        select(DailySteps.steps).where(
            DailySteps.user_id == user_id,
            DailySteps.date >= steps_cutoff,
        )
    )
    step_values = [r[0] for r in steps_res.all()]
    if step_values:
        avg_steps = sum(step_values) // len(step_values)
        # Activity tiers: <5K=-100, 5-8K=0, 8-12K=+100, >12K=+200
        if avg_steps < 5000:
            adherence_summary["steps_calorie_adjust"] = -100
        elif avg_steps < 8000:
            adherence_summary["steps_calorie_adjust"] = 0
        elif avg_steps < 12000:
            adherence_summary["steps_calorie_adjust"] = 100
        else:
            adherence_summary["steps_calorie_adjust"] = 200
        adherence_summary["avg_daily_steps"] = avg_steps

    # 3. Call Service
    service = _get_planning_service()
    
    last_revision_dates = {}
    for area in ["workout", "nutrition"]:
        last_date_res = await db.execute(
            select(PlanRevision.created_at)
            .where(
                PlanRevision.user_id == user_id,
                PlanRevision.status.in_(["pending", "applied", "approved"]),
                or_(PlanRevision.target_area == area, PlanRevision.target_area == "both")
            )
            .order_by(desc(PlanRevision.created_at))
            .limit(1)
        )
        last_date = last_date_res.scalar_one_or_none()
        if last_date:
            last_revision_dates[area] = last_date

    # Extract per-user sensitivity settings (with defaults from Replanner)
    sensitivity_settings = {}
    if profile:
        if profile.replan_weight_threshold_kg is not None:
            sensitivity_settings["weight_threshold_kg"] = profile.replan_weight_threshold_kg
        if profile.replan_missed_workout_threshold is not None:
            sensitivity_settings["missed_workout_threshold"] = profile.replan_missed_workout_threshold
        if profile.replan_cooldown_days is not None:
            sensitivity_settings["cooldown_days"] = profile.replan_cooldown_days

    trigger, reason, patch, updated_plan_dict, is_auto = await service.replan_active_plan(
        user_id,
        {"workout_plan": plan.workout_plan, "meal_plan": plan.meal_plan},
        adherence_summary,
        weight_delta,
        profile.goal if profile else "maintenance",
        last_revision_dates,
        sensitivity_settings
    )

    # 4. Determine target area
    target_area = _infer_target_area(trigger, patch)

    # 5. Determine status
    status = "applied" if is_auto else "pending"

    # 6. Get next revision number
    rev_number = await _get_next_revision_number(db, plan.id)

    # 7. Save Revision
    revision = PlanRevision(
        plan_id=plan.id,
        user_id=user_id,
        revision_number=rev_number,
        trigger=trigger,
        target_area=target_area,
        reason=reason,
        patch=patch,
        status=status,
        is_auto_applied=is_auto
    )
    db.add(revision)
    await db.flush()  # Get the ID for supersession

    # 8. Supersede older active revisions for the same area
    superseded_count = await _supersede_active_revisions(
        db, plan.id, target_area, revision.id, trigger
    )
    if superseded_count > 0:
        logger.info(
            "revisions_superseded",
            count=superseded_count,
            target_area=target_area,
            new_revision_id=revision.id,
        )

    # 9. Only Patch plan if auto-applied
    if is_auto:
        plan.workout_plan = updated_plan_dict["workout_plan"]
        plan.meal_plan = updated_plan_dict["meal_plan"]

    await db.commit()
    await db.refresh(revision)
    return revision


@router.post("/replan/approve/{revision_id}", response_model=PlanRevisionResponse)
async def approve_replan(revision_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PlanRevision).where(PlanRevision.id == revision_id))
    revision = res.scalar_one_or_none()
    if not revision: raise HTTPException(status_code=404, detail="Revision not found")

    if revision.status in TERMINAL_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve revision in '{revision.status}' state: {revision.status_reason or ''}"
        )

    if revision.status in ("approved", "applied"):
        return revision  # Already active

    # Apply the patch to the main plan
    res = await db.execute(select(WeeklyPlan).where(WeeklyPlan.id == revision.plan_id))
    plan = res.scalar_one_or_none()
    if not plan: raise HTTPException(status_code=404, detail="Parent plan not found")

    # We need the replanner to apply the patch
    _service = _get_planning_service()
    updated_plan = _service.replanner.apply_patch_to_plan(
        {"workout_plan": plan.workout_plan, "meal_plan": plan.meal_plan},
        revision.patch
    )

    plan.workout_plan = updated_plan["workout_plan"]
    plan.meal_plan = updated_plan["meal_plan"]

    revision.status = "approved"
    await db.commit()
    await db.refresh(revision)
    return revision


@router.post("/replan/undo/{revision_id}", response_model=PlanRevisionResponse)
async def revert_replan(revision_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Reverse an auto-applied revision by creating a compensating patch.
    Marks the original as 'reverted' (not deleted) to preserve audit trail.
    """
    res = await db.execute(select(PlanRevision).where(PlanRevision.id == revision_id))
    revision = res.scalar_one_or_none()

    if not revision: raise HTTPException(status_code=404, detail="Revision not found")

    if revision.status in TERMINAL_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot undo revision in '{revision.status}' state: {revision.status_reason or ''}"
        )

    if not revision.is_auto_applied and revision.status != "approved":
        raise HTTPException(status_code=400, detail="Only applied/approved revisions can be undone")

    # 1. Get current plan
    res = await db.execute(select(WeeklyPlan).where(WeeklyPlan.id == revision.plan_id))
    plan = res.scalar_one_or_none()
    if not plan: raise HTTPException(status_code=404, detail="Parent plan not found")

    # 2. Planning Service logic
    service = _get_planning_service()
    trigger, reason, reversal_patch, updated_plan = await service.undo_replan(
        revision.user_id,
        revision.patch,
        {"workout_plan": plan.workout_plan, "meal_plan": plan.meal_plan}
    )

    # 3. Get next revision number
    rev_number = await _get_next_revision_number(db, plan.id)

    # 4. Create the compensating revision
    comp_revision = PlanRevision(
        plan_id=plan.id,
        user_id=revision.user_id,
        revision_number=rev_number,
        trigger=trigger,
        target_area=revision.target_area,  # Same area as the original
        reason=reason,
        patch=reversal_patch,
        status="applied",
        is_auto_applied=False,
        parent_revision_id=revision.id,  # Link to the original revision
    )
    db.add(comp_revision)
    await db.flush()  # get ID

    # 5. Mark original as reverted (not deleted)
    revision.status = "reverted"
    revision.status_reason = "Reverted by user"
    revision.undone_at = func.now()
    revision.undone_by_id = comp_revision.id

    # 6. Apply to plan
    plan.workout_plan = updated_plan["workout_plan"]
    plan.meal_plan = updated_plan["meal_plan"]

    await db.commit()
    await db.refresh(comp_revision)
    return comp_revision


@router.get("/revisions/{plan_id}", response_model=list[PlanRevisionResponse])
async def get_plan_revisions(plan_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Get all revisions for a plan, ordered newest first.
    Includes status labels for UI display.
    """
    result = await db.execute(
        select(PlanRevision)
        .where(PlanRevision.plan_id == plan_id)
        .order_by(desc(PlanRevision.created_at))
    )
    revisions = result.scalars().all()
    return revisions


@router.get("/revisions/user", response_model=list[PlanRevisionResponse])
async def get_user_revisions(limit: int = 20, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = current_user.id
    """
    Get all revisions for a user across all plans, ordered newest first.
    """
    result = await db.execute(
        select(PlanRevision)
        .where(PlanRevision.user_id == user_id)
        .order_by(desc(PlanRevision.created_at))
        .limit(limit)
    )
    revisions = result.scalars().all()
    return revisions
