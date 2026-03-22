"""
AI Fitness Coach v1 — Meal & Recipe Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class MacroBreakdown(BaseModel):
    """Macro nutrient breakdown."""
    calories: int = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: Optional[float] = None


class RecipeInfo(BaseModel):
    """A recipe summary for meal planning."""
    id: Optional[int] = None  # Tandoor recipe ID
    name: str
    macros: MacroBreakdown
    prep_time_min: Optional[int] = None
    cook_time_min: Optional[int] = None
    servings: int = 1
    tags: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    goal_fit: Optional[str] = None  # "excellent" | "good" | "fair"


class MealSlot(BaseModel):
    """A single meal within a day."""
    meal_type: str  # breakfast | lunch | dinner | snack_1 | snack_2
    recipe: RecipeInfo
    servings: float = 1.0
    notes: Optional[str] = None


class MealDay(BaseModel):
    """A single day's meal plan."""
    day: str  # "Monday", etc.
    day_number: int = Field(..., ge=1, le=7)
    meals: list[MealSlot] = Field(default_factory=list)
    totals: MacroBreakdown = Field(default_factory=MacroBreakdown)


class MealPlan(BaseModel):
    """A complete weekly meal plan."""
    days: list[MealDay]
    weekly_totals: MacroBreakdown = Field(default_factory=MacroBreakdown)
    notes: Optional[str] = None


class ShoppingItem(BaseModel):
    """A single item on the shopping list."""
    name: str
    quantity: str
    unit: Optional[str] = None
    category: str = "Other"
    # Produce | Protein | Dairy | Grains | Pantry | Frozen | Other
    checked: bool = False
    recipe_source: Optional[str] = None


class ShoppingList(BaseModel):
    """Aggregated shopping list from the meal plan."""
    items: list[ShoppingItem] = Field(default_factory=list)
    week_start: Optional[datetime] = None
    generated_from_plan_id: Optional[str] = None


class RecipeImportRequest(BaseModel):
    """Schema for importing a recipe from a URL."""
    url: str
    notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


# --- Meal Logging Schemas ---

class MealLogCreate(BaseModel):
    """Schema for logging a consumed meal."""
    meal_type: str = Field(..., description="breakfast | lunch | dinner | snack | other")
    name: str = Field(..., min_length=1, max_length=200)
    calories: int = Field(0, ge=0)
    protein_g: float = Field(0, ge=0)
    carbs_g: float = Field(0, ge=0)
    fat_g: float = Field(0, ge=0)
    servings: float = Field(1.0, gt=0)
    date: Optional[datetime] = None  # Defaults to now if not provided
    notes: Optional[str] = None
    is_planned: bool = False  # True if marking a planned meal as eaten


class MealLogResponse(BaseModel):
    """Response schema for a logged meal."""
    id: str
    user_id: str
    plan_id: Optional[str] = None
    date: datetime
    meal_type: str
    name: str
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    servings: float
    is_planned: bool
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
