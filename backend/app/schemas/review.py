"""
AI Fitness Coach v1 — Weekly Review Schemas

Response models for the weekly review / coach insights endpoint.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class WeightSummary(BaseModel):
    """Weight trend summary for the week."""
    start_kg: Optional[float] = None
    current_kg: Optional[float] = None
    change_kg: Optional[float] = None
    trend: Optional[str] = None  # "losing" | "gaining" | "stable"
    aligned_with_goal: Optional[bool] = None


class WorkoutSummary(BaseModel):
    """Workout completion metrics for the week."""
    planned: int = 0
    completed: int = 0
    completion_pct: float = 0.0
    avg_energy: Optional[float] = None
    total_duration_min: int = 0


class NutritionSummary(BaseModel):
    """Nutrition adherence metrics for the week."""
    days_on_target: int = 0
    total_days: int = 0
    adherence_pct: float = 0.0
    avg_calories: Optional[int] = None
    target_calories: Optional[int] = None


class CoachAdjustment(BaseModel):
    """Summary of a plan revision / coach adjustment."""
    trigger: str
    area: str  # "workout" | "nutrition" | "both"
    change: str  # Human-readable description of the change
    status: str  # "applied" | "approved" | "pending" | "reverted" | "superseded"
    date: str  # ISO date string


class WeeklyReviewResponse(BaseModel):
    """Complete weekly analytics summary."""
    week_start: str
    week_end: str
    goal: Optional[str] = None

    weight: WeightSummary
    workouts: WorkoutSummary
    nutrition: NutritionSummary
    coach_adjustments: list[CoachAdjustment] = Field(default_factory=list)

    insights: list[str] = Field(default_factory=list)
    next_action: Optional[str] = None
    message: Optional[str] = None  # For empty states

    class Config:
        from_attributes = True


# --- Trends Endpoint Models ---


class WeekWeightPoint(BaseModel):
    """Single week weight data point."""
    week: str
    change_kg: Optional[float] = None
    trend: Optional[str] = None  # "losing" | "gaining" | "stable"
    aligned: Optional[bool] = None


class WeekWorkoutPoint(BaseModel):
    """Single week workout data point."""
    week: str
    completion_pct: float = 0.0
    completed: int = 0
    planned: int = 0


class WeekNutritionPoint(BaseModel):
    """Single week nutrition data point."""
    week: str
    adherence_pct: float = 0.0


class WeightTrends(BaseModel):
    """4-week weight trend summary."""
    weeks: list[WeekWeightPoint] = Field(default_factory=list)
    total_change_kg: Optional[float] = None
    direction: str = "insufficient_data"  # "up" | "down" | "stable"


class WorkoutTrends(BaseModel):
    """4-week workout trend summary."""
    weeks: list[WeekWorkoutPoint] = Field(default_factory=list)
    avg_completion_pct: float = 0.0
    direction: str = "insufficient_data"  # "up" | "down" | "stable"


class NutritionTrends(BaseModel):
    """4-week nutrition trend summary."""
    weeks: list[WeekNutritionPoint] = Field(default_factory=list)
    avg_adherence_pct: float = 0.0
    direction: str = "insufficient_data"  # "up" | "down" | "stable"


class TrendsSummary(BaseModel):
    """Combined trends for all metrics."""
    weight: WeightTrends
    workouts: WorkoutTrends
    nutrition: NutritionTrends


class RevisionFrequency(BaseModel):
    """Coach adjustment frequency analysis."""
    total: int = 0
    auto_applied: int = 0
    user_approved: int = 0
    undone: int = 0
    superseded: int = 0
    assessment: str = "stable"  # "stable" | "moderate" | "active"


class GoalAlignment(BaseModel):
    """Goal alignment status."""
    status: str = "insufficient_data"  # "on_track" | "mixed" | "off_track"
    weight_aligned_weeks: int = 0
    workout_target_weeks: int = 0
    nutrition_target_weeks: int = 0


class TrendsResponse(BaseModel):
    """Complete 4-week analytics trends response."""
    user_id: str
    goal: Optional[str] = None
    period: str = "4 weeks"

    trends: TrendsSummary
    revision_frequency: RevisionFrequency
    goal_alignment: GoalAlignment
    message: Optional[str] = None  # For empty states

    class Config:
        from_attributes = True
