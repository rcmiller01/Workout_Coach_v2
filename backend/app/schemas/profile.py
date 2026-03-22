"""
AI Fitness Coach v1 — Profile Schemas (Pydantic v2)
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class InjuryDetail(BaseModel):
    area: str = Field(..., description="Body area affected", examples=["left_knee", "lower_back"])
    severity: str = Field("mild", description="mild | moderate | severe")
    notes: Optional[str] = None


class ProfileCreate(BaseModel):
    """Schema for creating a new user profile."""
    user_id: str

    # Goals
    goal: str = Field("maintenance", description="fat_loss | muscle_gain | maintenance | general_fitness")

    # Equipment & Schedule
    equipment: list[str] = Field(default_factory=list, examples=[["rack", "dumbbells", "cables", "barbell"]])
    days_per_week: int = Field(4, ge=1, le=7)
    session_length_min: int = Field(45, ge=15, le=180)
    preferred_workout_time: str = Field("morning", description="morning | afternoon | evening")

    # Diet / Nutrition
    target_calories: int = Field(2200, ge=1000, le=6000)
    target_protein_g: int = Field(180, ge=50, le=400)
    target_carbs_g: Optional[int] = Field(None, ge=0)
    target_fat_g: Optional[int] = Field(None, ge=0)
    dietary_restrictions: list[str] = Field(default_factory=list)
    dietary_preferences: list[str] = Field(default_factory=list)

    # Health
    injuries: list[InjuryDetail] = Field(default_factory=list)
    health_conditions: list[str] = Field(default_factory=list)

    # Body Metrics
    height_cm: Optional[float] = Field(None, ge=100, le=250)
    weight_kg: Optional[float] = Field(None, ge=30, le=300)
    age: Optional[int] = Field(None, ge=13, le=100)
    sex: Optional[str] = Field(None, description="male | female | other")
    body_fat_pct: Optional[float] = Field(None, ge=3, le=60)
    activity_level: str = Field("moderate", description="sedentary | light | moderate | active | very_active")

    # Coaching
    coaching_persona: str = Field("supportive", description="direct | supportive | technical | quiet")


class ProfileUpdate(BaseModel):
    """Schema for updating an existing profile (all fields optional)."""
    goal: Optional[str] = None
    equipment: Optional[list[str]] = None
    days_per_week: Optional[int] = Field(None, ge=1, le=7)
    session_length_min: Optional[int] = Field(None, ge=15, le=180)
    preferred_workout_time: Optional[str] = None
    target_calories: Optional[int] = Field(None, ge=1000, le=6000)
    target_protein_g: Optional[int] = Field(None, ge=50, le=400)
    target_carbs_g: Optional[int] = None
    target_fat_g: Optional[int] = None
    dietary_restrictions: Optional[list[str]] = None
    dietary_preferences: Optional[list[str]] = None
    injuries: Optional[list[InjuryDetail]] = None
    health_conditions: Optional[list[str]] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    body_fat_pct: Optional[float] = None
    activity_level: Optional[str] = None
    coaching_persona: Optional[str] = None


class ProfileResponse(BaseModel):
    """Schema for profile API responses."""
    id: str
    user_id: str
    goal: str
    equipment: list[str]
    days_per_week: int
    session_length_min: int
    preferred_workout_time: str
    target_calories: int
    target_protein_g: int
    target_carbs_g: Optional[int]
    target_fat_g: Optional[int]
    dietary_restrictions: list[str]
    dietary_preferences: list[str]
    injuries: list[dict]
    health_conditions: list[str]
    height_cm: Optional[float]
    weight_kg: Optional[float]
    age: Optional[int]
    sex: Optional[str]
    body_fat_pct: Optional[float]
    activity_level: str
    coaching_persona: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
