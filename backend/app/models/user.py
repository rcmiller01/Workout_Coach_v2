"""
AI Fitness Coach v1 — User & Profile Models
"""
from sqlalchemy import Column, String, Integer, Float, JSON, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.database import Base
import uuid


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """User account — minimal auth for local/self-hosted use."""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    # External provider tokens (stored for server-side API calls)
    wger_token = Column(String(255), nullable=True)
    tandoor_token = Column(String(255), nullable=True)


class UserProfile(Base):
    """
    Canonical user profile — the orchestration layer's understanding
    of the user's goals, constraints, and preferences.
    """
    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False, unique=True, index=True)

    # --- Goals ---
    goal = Column(String(50), nullable=False, default="maintenance")
    # fat_loss | muscle_gain | maintenance | general_fitness

    # --- Equipment & Schedule ---
    equipment = Column(JSON, default=list)
    # ["rack", "dumbbells", "cables", "barbell", "bench", "bodyweight"]

    days_per_week = Column(Integer, default=4)
    session_length_min = Column(Integer, default=45)
    preferred_workout_time = Column(String(20), default="morning")
    # morning | afternoon | evening

    # --- Diet / Nutrition ---
    target_calories = Column(Integer, default=2200)
    target_protein_g = Column(Integer, default=180)
    target_carbs_g = Column(Integer, nullable=True)
    target_fat_g = Column(Integer, nullable=True)
    dietary_restrictions = Column(JSON, default=list)
    # ["vegetarian", "gluten_free", "low_sugar", "dairy_free", "keto", ...]
    dietary_preferences = Column(JSON, default=list)
    # ["high_protein", "quick_meals", "meal_prep_friendly", ...]

    # --- Health ---
    injuries = Column(JSON, default=list)
    # [{"area": "left_knee", "severity": "moderate", "notes": "ACL repair 2023"}]
    health_conditions = Column(JSON, default=list)
    # ["hypertension", "diabetes_t2", ...]

    # --- Body Metrics (snapshot for planning) ---
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    age = Column(Integer, nullable=True)
    sex = Column(String(10), nullable=True)  # male | female | other
    body_fat_pct = Column(Float, nullable=True)
    activity_level = Column(String(20), default="moderate")
    # sedentary | light | moderate | active | very_active

    # --- Workout Preferences ---
    workout_notes = Column(Text, nullable=True)
    # Freeform text: "full kettlebell workout", "cardio only on Tuesdays",
    # "no barbell squats", "prefer compound movements"

    # --- Coaching Preferences ---
    coaching_persona = Column(String(20), default="supportive")
    # direct | supportive | technical | quiet

    # --- Replan Sensitivity Settings ---
    # Weight trend threshold (kg) before triggering calorie adjustments
    replan_weight_threshold_kg = Column(Float, default=0.5)
    # Missed workout count before triggering volume reductions
    replan_missed_workout_threshold = Column(Integer, default=2)
    # Cooldown window (days) between revisions in the same target area
    replan_cooldown_days = Column(Integer, default=3)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class WeightEntry(Base):
    """
    Weight tracking entries — supports both manual logging and external sync.

    Source types:
        - manual: User-entered via app
        - healthkit: Synced from Apple HealthKit
        - google_fit: Synced from Google Fit
        - import: Bulk imported from CSV/file
    """
    __tablename__ = "weight_entries"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False, index=True)
    weight_kg = Column(Float, nullable=False)
    date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    notes = Column(Text, nullable=True)

    # --- Source Metadata ---
    source = Column(String(20), default="manual", nullable=False)
    # manual | healthkit | google_fit | import

    # External ID from sync source (for deduplication)
    source_id = Column(String(255), nullable=True, index=True)

    # Timestamp when this entry was synced from external source
    synced_at = Column(DateTime(timezone=True), nullable=True)

    # --- wger Sync ---
    synced_to_wger = Column(String(20), default="pending")
    # pending | synced | failed | skipped

    created_at = Column(DateTime(timezone=True), server_default=func.now())

