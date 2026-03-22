"""
AI Fitness Coach v1 — Workout Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ExerciseSet(BaseModel):
    """A single set within an exercise."""
    reps: int = Field(..., ge=1)
    weight_kg: Optional[float] = Field(None, ge=0)
    duration_sec: Optional[int] = Field(None, ge=0)
    rpe: Optional[int] = Field(None, ge=1, le=10, description="Rate of perceived exertion")
    rir: Optional[int] = Field(None, ge=0, le=5, description="Reps in reserve")


class ExercisePlan(BaseModel):
    """A planned exercise within a workout day."""
    name: str
    exercise_id: Optional[int] = None  # wger exercise ID
    muscle_group: Optional[str] = None
    sets: int = Field(3, ge=1, le=10)
    reps: str = Field("8-10", description="Rep range as string")
    weight_kg: Optional[float] = None
    rest_sec: int = Field(90, description="Rest between sets in seconds")
    notes: Optional[str] = None
    substitutions: list[str] = Field(default_factory=list)


class WorkoutDay(BaseModel):
    """A single day's workout plan."""
    day: str  # "Monday", "Tuesday", etc.
    day_number: int = Field(..., ge=1, le=7)
    focus: str  # "Upper Body Push", "Lower Body", "Rest", etc.
    is_rest_day: bool = False
    exercises: list[ExercisePlan] = Field(default_factory=list)
    estimated_duration_min: int = 45
    warmup_notes: Optional[str] = None
    cooldown_notes: Optional[str] = None


class WorkoutPlan(BaseModel):
    """A complete weekly workout plan."""
    days: list[WorkoutDay]
    total_training_days: int
    split_type: str = "push_pull_legs"  # ppl | upper_lower | full_body | bro_split
    notes: Optional[str] = None


class WorkoutLogCreate(BaseModel):
    """Schema for logging a completed workout."""
    plan_id: Optional[str] = None
    date: datetime
    exercises_completed: list[dict]
    # [{"name": "Bench Press", "sets": [{"reps": 10, "weight_kg": 80}, ...]}]
    completion_pct: float = Field(1.0, ge=0, le=1)
    duration_min: Optional[int] = None
    energy_level: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None


class WorkoutLogResponse(BaseModel):
    """Schema for workout log API response."""
    id: str
    user_id: str
    plan_id: Optional[str]
    date: datetime
    exercises_completed: list[dict]
    completion_pct: float
    duration_min: Optional[int]
    energy_level: Optional[int]
    notes: Optional[str]
    synced_to_wger: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True
