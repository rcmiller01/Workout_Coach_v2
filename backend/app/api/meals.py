"""
AI Fitness Coach v1 — Meals API Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime
from app.database import get_db
from app.models.plan import WeeklyPlan
from app.schemas.meal import RecipeImportRequest, MealLogCreate, MealLogResponse
from app.models.plan import MealLog
from app.providers import TandoorProvider
from app.config import settings

router = APIRouter(prefix="/meals", tags=["Meals"])


@router.get("/today/{user_id}")
async def get_todays_meals(user_id: str, db: AsyncSession = Depends(get_db)):
    """Get today's planned meals and the active nutrition revision context."""
    from app.models.user import UserProfile
    from app.models.plan import PlanRevision
    from app.schemas.plan import PlanRevisionResponse

    # 1. Get Plan & Profile
    result = await db.execute(
        select(WeeklyPlan)
        .where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
        .order_by(desc(WeeklyPlan.created_at))
        .limit(1)
    )
    plan = result.scalar_one_or_none()

    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()
    
    # Baseline Targets
    baseline_targets = {
        "calories": profile.target_calories if profile else 2000,
        "protein_g": profile.target_protein_g if profile else 150,
        "carbs_g": profile.target_carbs_g if profile else 200,
        "fat_g": profile.target_fat_g if profile else 70,
    }

    if not plan:
        return {
            "message": "No active plan", 
            "meals": [], 
            "baseline_targets": baseline_targets,
            "current_targets": baseline_targets,
            "nutrition_revisions": []
        }

    # 2. Get Nutrition Revisions for this plan (ordered from newest to oldest)
    # The effective target comes from processing the revision chain or superseding logic.
    # Since superseding is built-in, the FIRST 'applied' or 'approved' revision for 'nutrition' forms the delta.
    # We will return the history so the UI can show before vs after and terminal states.
    rev_result = await db.execute(
        select(PlanRevision)
        .where(
            PlanRevision.plan_id == plan.id,
            PlanRevision.target_area.in_(["nutrition", "both"])
        )
        .order_by(desc(PlanRevision.created_at))
    )
    db_revisions = rev_result.scalars().all()
    
    # Current Targets Start at Baseline
    current_targets = baseline_targets.copy()

    # Build revision impact summary for active adjustments
    active_adjustments = []
    effective_cal_adjust = 0

    # Apply the single valid "effective active" patch from the chain if one exists
    effective_rev = next((r for r in db_revisions if r.status in ("applied", "approved", "pending")), None)

    if effective_rev:
        # pending revisions haven't hit the plan dictionary yet, but mathematically
        # we can show the "proposed" current targets vs what is active.
        cal_adjust = effective_rev.patch.get("meal_plan", {}).get("calorie_adjust", 0)
        current_targets["calories"] += cal_adjust
        effective_cal_adjust = cal_adjust
        # If there are protein/carb adjustments, we would apply them here.

        if cal_adjust != 0:
            sign = "+" if cal_adjust > 0 else ""
            active_adjustments.append(f"calories {sign}{cal_adjust}")

    today = datetime.now()
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    today_name = day_names[today.weekday()]

    meal_plan = plan.meal_plan or {}
    today_meals = None

    for day in meal_plan.get("days", []):
        if day.get("day", "").lower() == today_name.lower():
            today_meals = day
            break

    # Build impact summary string
    impact_summary = None
    if active_adjustments:
        impact_summary = f"This week's active adjustments: {', '.join(active_adjustments)}"

    return {
        "date": today.strftime("%Y-%m-%d"),
        "day": today_name,
        "meals": today_meals.get("meals", []) if today_meals else [],
        "totals": today_meals.get("totals", {}) if today_meals else {},
        "plan_id": plan.id,
        "baseline_targets": baseline_targets,
        "current_targets": current_targets,
        "impact_summary": impact_summary,
        # Convert ORM to Pydantic strings/dicts safely to pass back to frontend
        "nutrition_revisions": [PlanRevisionResponse.model_validate(r).model_dump(mode='json') for r in db_revisions],
    }


@router.get("/plan/{user_id}")
async def get_meal_plan(user_id: str, db: AsyncSession = Depends(get_db)):
    """Get the current full meal plan."""
    result = await db.execute(
        select(WeeklyPlan)
        .where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
        .order_by(desc(WeeklyPlan.created_at))
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No active meal plan")

    return {
        "plan_id": plan.id,
        "week_start": plan.week_start.isoformat() if plan.week_start else None,
        "meal_plan": plan.meal_plan,
    }


@router.post("/import-recipe")
async def import_recipe(request: RecipeImportRequest):
    """Import a recipe from a URL via Tandoor."""
    tandoor = TandoorProvider(
        base_url=settings.tandoor_base_url,
        api_token=settings.tandoor_api_token,
    )

    try:
        result = await tandoor.import_recipe_url(request.url)
        return {
            "status": "imported",
            "recipe": result,
            "message": f"Recipe imported from {request.url}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import recipe: {str(e)}",
        )
    finally:
        await tandoor.close()


from pydantic import BaseModel
from typing import Optional

class MacroEstimateRequest(BaseModel):
    meal_name: str
    meal_type: str = "other"
    notes: Optional[str] = None


@router.post("/estimate-macros")
async def estimate_macros(request: MacroEstimateRequest):
    """Use LLM to estimate macros for a meal description."""
    import litellm
    import json

    description = request.meal_name
    if request.notes:
        description += f" ({request.notes})"

    prompt = f"""Estimate the nutritional content for this meal:

Meal: {description}
Meal type: {request.meal_type}

Provide your best estimate for a typical serving. Return ONLY valid JSON in this exact format:
{{
    "calories": <integer>,
    "protein_g": <number>,
    "carbs_g": <number>,
    "fat_g": <number>,
    "confidence": "<low|medium|high>",
    "notes": "<brief explanation of estimate>"
}}

Be realistic and use common portion sizes. If the description is vague, estimate for a typical restaurant-sized portion."""

    try:
        model_string = f"ollama/{settings.llm_model}" if settings.llm_provider == "ollama" else settings.llm_model

        response = await litellm.acompletion(
            model=model_string,
            messages=[
                {"role": "system", "content": "You are a nutritionist expert. Estimate macros accurately based on typical portion sizes. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500,
            api_base=settings.llm_base_url if settings.llm_provider == "ollama" else None,
            timeout=60,
        )

        content = response.choices[0].message.content

        # Strip thinking tags if present
        if "<think>" in content:
            content = content.split("</think>")[-1].strip()

        # Parse JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown blocks
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                result = json.loads(content[start:end].strip())
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                result = json.loads(content[start:end].strip())
            else:
                # Try boundary finding
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(content[start:end])
                else:
                    raise ValueError("Could not parse JSON from LLM response")

        return {
            "calories": int(result.get("calories", 0)),
            "protein_g": float(result.get("protein_g", 0)),
            "carbs_g": float(result.get("carbs_g", 0)),
            "fat_g": float(result.get("fat_g", 0)),
            "confidence": result.get("confidence", "medium"),
            "ai_notes": result.get("notes", ""),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to estimate macros: {str(e)}",
        )


@router.post("/log", response_model=MealLogResponse, status_code=201)
async def log_meal(data: MealLogCreate, user_id: str, db: AsyncSession = Depends(get_db)):
    """Log a consumed meal (custom or from plan)."""
    # Get active plan ID if exists
    plan_id = None
    if data.is_planned:
        result = await db.execute(
            select(WeeklyPlan)
            .where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
            .order_by(desc(WeeklyPlan.created_at))
            .limit(1)
        )
        plan = result.scalar_one_or_none()
        if plan:
            plan_id = plan.id

    log = MealLog(
        user_id=user_id,
        plan_id=plan_id,
        date=data.date or datetime.now(),
        meal_type=data.meal_type,
        name=data.name,
        calories=data.calories,
        protein_g=data.protein_g,
        carbs_g=data.carbs_g,
        fat_g=data.fat_g,
        servings=data.servings,
        is_planned=data.is_planned,
        notes=data.notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.get("/history/{user_id}")
async def get_meal_history(
    user_id: str,
    limit: int = 50,
    date: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Get meal log history for a user. Optionally filter by date (YYYY-MM-DD)."""
    query = select(MealLog).where(MealLog.user_id == user_id)

    if date:
        # Filter by specific date
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
            next_day = datetime(target_date.year, target_date.month, target_date.day + 1)
            query = query.where(MealLog.date >= target_date, MealLog.date < next_day)
        except ValueError:
            pass  # Invalid date format, ignore filter

    query = query.order_by(desc(MealLog.date)).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    entries = [
        {
            "id": log.id,
            "date": log.date.isoformat() if log.date else None,
            "meal_type": log.meal_type,
            "name": log.name,
            "calories": log.calories,
            "protein_g": log.protein_g,
            "carbs_g": log.carbs_g,
            "fat_g": log.fat_g,
            "servings": log.servings,
            "is_planned": log.is_planned,
            "notes": log.notes,
        }
        for log in logs
    ]

    # Calculate totals for the day if date filter is applied
    totals = None
    if date and entries:
        totals = {
            "calories": sum(e["calories"] for e in entries),
            "protein_g": sum(e["protein_g"] for e in entries),
            "carbs_g": sum(e["carbs_g"] for e in entries),
            "fat_g": sum(e["fat_g"] for e in entries),
        }

    return {
        "entries": entries,
        "count": len(entries),
        "totals": totals,
        "message": None if entries else "No meal logs yet - log your first meal!",
    }
