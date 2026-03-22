"""
AI Fitness Coach v1 — Plan Models
"""
from sqlalchemy import Column, String, Integer, JSON, DateTime, Text, Float, ForeignKey, Boolean

from sqlalchemy.sql import func
from app.database import Base
import uuid


def generate_uuid() -> str:
    return str(uuid.uuid4())


class WeeklyPlan(Base):
    """
    A generated weekly plan — contains both workout and meal plan data.
    Plans are immutable snapshots; replanning creates a new plan.
    """
    __tablename__ = "weekly_plans"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False, index=True)

    # --- Plan Metadata ---
    week_start = Column(DateTime(timezone=True), nullable=False)
    week_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="active")
    # draft | active | completed | replaced

    # --- Generated Plans (stored as structured JSON) ---
    workout_plan = Column(JSON, default=dict)
    # {
    #   "days": [
    #     {
    #       "day": "Monday",
    #       "focus": "Upper Body Push",
    #       "exercises": [
    #         {"name": "Bench Press", "sets": 4, "reps": "8-10", "weight_kg": 80, "rest_sec": 120},
    #         ...
    #       ]
    #     },
    #     ...
    #   ]
    # }

    meal_plan = Column(JSON, default=dict)
    # {
    #   "days": [
    #     {
    #       "day": "Monday",
    #       "meals": [
    #         {"type": "breakfast", "recipe_id": 42, "name": "Protein Oats", "calories": 450, "protein_g": 35},
    #         ...
    #       ],
    #       "totals": {"calories": 2200, "protein_g": 185, "carbs_g": 220, "fat_g": 65}
    #     }
    #   ]
    # }

    shopping_list = Column(JSON, default=list)
    # [
    #   {"item": "Chicken Breast", "quantity": "2 kg", "category": "Protein"},
    #   ...
    # ]

    # --- LLM Generation Context ---
    llm_reasoning = Column(Text, nullable=True)
    # The LLM's reasoning for this plan (for transparency)

    rules_applied = Column(JSON, default=list)
    # ["volume_cap_adjusted", "protein_minimum_enforced", ...]

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkoutLog(Base):
    """
    Local log of workout completion (also synced to wger).
    """
    __tablename__ = "workout_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False, index=True)
    plan_id = Column(String, nullable=True)
    date = Column(DateTime(timezone=True), nullable=False)

    # --- Completion Data ---
    exercises_completed = Column(JSON, default=list)
    # [
    #   {"name": "Bench Press", "sets": [{"reps": 10, "weight_kg": 80}, ...]},
    #   ...
    # ]

    completion_pct = Column(Float, default=0.0)
    duration_min = Column(Integer, nullable=True)
    energy_level = Column(Integer, nullable=True)  # 1-5 scale
    notes = Column(Text, nullable=True)

    # --- Sync Status ---
    synced_to_wger = Column(String(20), default="pending")
    # pending | synced | failed
    wger_log_ids = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AdherenceRecord(Base):
    """
    Daily adherence tracking — feeds into adaptive replanning.
    """
    __tablename__ = "adherence_records"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False, index=True)
    date = Column(DateTime(timezone=True), nullable=False)

    # --- Workout Adherence ---
    workout_planned = Column(String(10), default="false")
    workout_completed = Column(String(10), default="false")
    workout_completion_pct = Column(Float, default=0.0)

    # --- Nutrition Adherence ---
    meals_planned = Column(Integer, default=0)
    meals_followed = Column(Integer, default=0)
    calories_actual = Column(Integer, nullable=True)
    protein_actual_g = Column(Integer, nullable=True)

    # --- User Feedback ---
    energy_level = Column(Integer, nullable=True)  # 1-5
    hunger_level = Column(Integer, nullable=True)  # 1-5
    sleep_quality = Column(Integer, nullable=True)  # 1-5
    mood = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MealLog(Base):
    """
    Log of meals consumed (both planned and custom/unplanned meals).
    """
    __tablename__ = "meal_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False, index=True)
    plan_id = Column(String, nullable=True)  # Null if custom/unplanned meal
    date = Column(DateTime(timezone=True), nullable=False)

    # --- Meal Data ---
    meal_type = Column(String(20), nullable=False)
    # breakfast | lunch | dinner | snack | other
    name = Column(String(200), nullable=False)

    # --- Macros ---
    calories = Column(Integer, default=0)
    protein_g = Column(Float, default=0)
    carbs_g = Column(Float, default=0)
    fat_g = Column(Float, default=0)

    # --- Meta ---
    servings = Column(Float, default=1.0)
    is_planned = Column(Boolean, default=False)  # True if from weekly plan
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PlanRevision(Base):
    """
    Incremental adjustment to an existing WeeklyPlan.
    Stores the 'delta' instead of a full regeneration.

    Status lifecycle:
        pending   → approved (user accepts) or superseded/blocked
        applied   → reverted (user undoes) or superseded
        approved  → reverted (user undoes)
        reverted  → terminal
        superseded→ terminal
        blocked   → terminal
    """
    __tablename__ = "plan_revisions"

    id = Column(String, primary_key=True, default=generate_uuid)
    plan_id = Column(String, ForeignKey("weekly_plans.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)

    revision_number = Column(Integer, default=1)

    # missed_workout | calorie_adjust | volume_adjust | exercise_swap | user_undo
    trigger = Column(String(50), nullable=False)

    # What area of the plan this revision targets
    # workout | nutrition | both
    target_area = Column(String(20), default="both")

    # Audit trail: "Reducing volume by 15% due to 2 missed sessions"
    reason = Column(Text, nullable=False)

    # JSON patch or list of modified day indices
    patch = Column(JSON, default=dict)

    # pending | applied | approved | reverted | superseded | blocked
    status = Column(String(20), default="applied")

    # Human-readable explanation for terminal states
    # e.g. "Superseded by newer calorie adjustment", "Reverted by user"
    status_reason = Column(Text, nullable=True)

    # True if the patch was applied immediately without user interaction
    is_auto_applied = Column(Boolean, default=True)

    # --- Revision Chain Links ---
    # Self-referential FK for dependent revision chains
    parent_revision_id = Column(String, ForeignKey("plan_revisions.id"), nullable=True)

    # ID of the revision that superseded this one (if any)
    superseded_by_id = Column(String, nullable=True)

    # Legacy undo tracking (kept for backwards compatibility, prefer status="reverted")
    undone_at = Column(DateTime(timezone=True), nullable=True)
    undone_by_id = Column(String, nullable=True)  # ID of the compensating revision

    created_at = Column(DateTime(timezone=True), server_default=func.now())


