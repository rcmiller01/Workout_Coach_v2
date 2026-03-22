"""
AI Fitness Coach v1 — Normalized Data Models

Internal, provider-agnostic schemas for the orchestration engine.
These models ensure the LLM planner and rules engine speak the same language,
regardless of whether the data comes from wger, Tandoor, or future providers.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime


class NormalizedMacros(BaseModel):
    """Calorie and macronutrient breakdown."""
    calories: int = Field(..., ge=0)
    protein_g: int = Field(..., ge=0)
    carbs_g: int = Field(..., ge=0)
    fat_g: int = Field(..., ge=0)

    @validator("calories")
    def validate_calories(cls, v, values):
        """Estimate calories based on macros to detect nonsense output."""
        if "protein_g" in values and "carbs_g" in values and "fat_g" in values:
            calc = (values["protein_g"] * 4) + (values["carbs_g"] * 4) + (values["fat_g"] * 9)
            # Allow 10% tolerance for rounding/fiber
            if abs(v - calc) > (v * 0.15 + 100):
                raise ValueError(f"Calories ({v}) inconsistent with macros ({calc})")
        return v


class NormalizedExercise(BaseModel):
    """A standardized exercise representation."""
    name: str
    muscle_group: str
    sets: int = Field(..., gt=0)
    reps: str  # Can be "8-10", "Fail", etc.
    weight_kg: float = Field(..., ge=0)
    rest_sec: int = Field(60, ge=0)
    notes: Optional[str] = ""
    substitutions: List[str] = []
    
    # Internal IDs
    provider_id: Optional[str] = None
    provider_name: str = "internal"


class NormalizedWorkoutDay(BaseModel):
    """A single day's workout session."""
    day: str
    day_number: int
    focus: str
    is_rest_day: bool = False
    estimated_duration_min: int = 0
    warmup_notes: Optional[str] = ""
    exercises: List[NormalizedExercise] = []


class NormalizedMeal(BaseModel):
    """A standardized meal/recipe representation."""
    meal_type: str  # breakfast, lunch, dinner, snack
    name: str
    servings: float = 1.0
    macros: NormalizedMacros
    recipe_id: Optional[str] = None  # Tandoor recipe ID
    notes: Optional[str] = ""


class NormalizedMealDay(BaseModel):
    """A single day's nutrition plan."""
    day: str
    day_number: int
    meals: List[NormalizedMeal]
    daily_totals: NormalizedMacros


class NormalizedPlan(BaseModel):
    """The full weekly orchestration plan."""
    plan_id: str
    user_id: str
    version: int = 1
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    
    week_start: str  # ISO date
    week_end: str    # ISO date
    
    workout_plan: List[NormalizedWorkoutDay]
    meal_plan: List[NormalizedMealDay]
    
    # Adherence tracking context
    is_replan: bool = False
    original_plan_id: Optional[str] = None
    
    rules_applied: List[str] = []
    metadata: dict = {}
