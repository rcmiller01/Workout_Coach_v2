"""
AI Fitness Coach v1 — Plan Schemas
"""
from pydantic import BaseModel, Field, computed_field
from typing import Optional
from datetime import datetime
from app.schemas.workout import WorkoutPlan
from app.schemas.meal import MealPlan, ShoppingList


class WeeklyPlanRequest(BaseModel):
    """Request to generate a new weekly plan."""
    user_id: str
    week_start: Optional[datetime] = None  # Defaults to next Monday
    force_regenerate: bool = False
    fast_mode: bool = False  # Generate shorter plan for speed
    custom_instructions: Optional[str] = None

    # e.g. "I'm traveling Monday-Wednesday, only bodyweight"


class WeeklyPlanResponse(BaseModel):
    """Response containing a complete weekly plan."""
    id: str
    user_id: str
    week_start: datetime
    week_end: datetime
    status: str

    workout_plan: dict | list
    meal_plan: dict | list
    shopping_list: list

    llm_reasoning: Optional[str]
    rules_applied: list[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class PlanRevisionResponse(BaseModel):
    """Full detail of a plan revision."""
    id: str
    plan_id: str
    revision_number: int
    trigger: str
    target_area: str = "both"
    reason: str
    patch: dict
    status: str
    status_reason: Optional[str] = None
    is_auto_applied: bool
    parent_revision_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    undone_at: Optional[datetime] = None
    undone_by_id: Optional[str] = None
    created_at: datetime

    @computed_field
    @property
    def status_label(self) -> str:
        """Human-friendly status label for the UI."""
        labels = {
            "pending": "⏳ Pending Approval",
            "applied": "✅ Auto-Applied",
            "approved": "👍 Approved by User",
            "reverted": f"↩️ {self.status_reason or 'Reverted by user'}",
            "superseded": f"⏭️ {self.status_reason or 'Superseded by newer revision'}",
            "blocked": f"🚫 {self.status_reason or 'Blocked'}",
        }
        return labels.get(self.status, self.status)

    class Config:
        from_attributes = True


class DashboardResponse(BaseModel):
    """Today's dashboard view — the primary screen."""
    date: str
    greeting: str
    coaching_message: Optional[str] = None

    # Today's workout
    workout: Optional[dict] = None
    workout_completed: bool = False

    # Today's meals
    meals: list[dict] = Field(default_factory=list)
    macro_targets: dict = Field(default_factory=dict)
    macro_actuals: Optional[dict] = None

    # Progress snapshot
    current_weight_kg: Optional[float] = None
    weight_trend: Optional[str] = None  # "down" | "up" | "stable"
    weekly_adherence_pct: Optional[float] = None

    # Upcoming
    next_workout: Optional[dict] = None
    shopping_list_count: int = 0

    # Revision History
    revisions: list[PlanRevisionResponse] = Field(default_factory=list)


class PlanAdjustmentRequest(BaseModel):
    """Request to adjust the current plan (adaptive replanning)."""
    user_id: str
    reason: str  # "missed_workout" | "weight_change" | "adherence_drop" | "user_request"
    details: Optional[str] = None
    specific_day: Optional[str] = None  # If adjusting a specific day


class WeightEntryRequest(BaseModel):
    """Log a manual weight entry."""
    user_id: str
    weight_kg: float
    notes: Optional[str] = None


class WeightSyncRequest(BaseModel):
    """Sync a weight entry from an external source (HealthKit, Google Fit, etc.)."""
    user_id: str
    weight_kg: float
    source: str = Field(..., pattern="^(healthkit|google_fit|import)$")
    source_id: Optional[str] = None  # External ID for deduplication
    measured_at: Optional[datetime] = None  # When the measurement was taken
    notes: Optional[str] = None


class WeightEntryResponse(BaseModel):
    """Weight entry with full metadata."""
    id: str
    user_id: str
    weight_kg: float
    date: datetime
    source: str
    source_id: Optional[str] = None
    synced_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LatestWeightResponse(BaseModel):
    """Latest weight with sync status."""
    weight_kg: float
    date: datetime
    source: str
    source_id: Optional[str] = None
    synced_at: Optional[datetime] = None
    last_sync_time: Optional[datetime] = None  # Most recent sync from any source
    trend: Optional[str] = None  # up | down | stable
    delta_kg: Optional[float] = None  # Change from previous entry


class WeightSyncResult(BaseModel):
    """Result of a weight sync operation."""
    status: str  # created | deduplicated | updated
    weight_entry: Optional[WeightEntryResponse] = None
    replan_triggered: bool = False
    revision_id: Optional[str] = None  # If replan was triggered
    message: str
