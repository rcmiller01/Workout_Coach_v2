"""
AI Fitness Coach v1 — Seed Data Service

Creates demo/test data for rapid development and testing.
Idempotent - can be called multiple times safely.
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision, WorkoutLog, AdherenceRecord
from app.logging_config import get_logger

logger = get_logger("seed_data")

# Demo user constants
DEMO_USER_ID = "demo-user-001"
DEMO_USERNAME = "demo_coach_user"


class SeedDataService:
    """
    Service for seeding demo data.

    All seed operations are idempotent - calling them multiple times
    produces the same result.
    """

    async def seed_demo_user(
        self,
        db: AsyncSession,
        user_id: str = DEMO_USER_ID,
        clear_existing: bool = False,
    ) -> dict:
        """
        Seed a complete demo user with all associated data.

        Args:
            user_id: The user ID to use (default: demo-user-001)
            clear_existing: If True, delete existing demo data first

        Returns:
            Summary of created entities
        """
        if clear_existing:
            await self._clear_user_data(db, user_id)

        summary = {
            "user_id": user_id,
            "created": {},
            "skipped": {},
        }

        # 1. Create User
        user = await self._seed_user(db, user_id)
        if user:
            summary["created"]["user"] = True
        else:
            summary["skipped"]["user"] = "already exists"

        # 2. Create Profile
        profile = await self._seed_profile(db, user_id)
        if profile:
            summary["created"]["profile"] = True
        else:
            summary["skipped"]["profile"] = "already exists"

        # 3. Create Weight History
        weight_count = await self._seed_weight_history(db, user_id)
        summary["created"]["weight_entries"] = weight_count

        # 4. Create Weekly Plan
        plan = await self._seed_weekly_plan(db, user_id)
        if plan:
            summary["created"]["plan"] = plan.id
        else:
            summary["skipped"]["plan"] = "already exists"

        # 5. Create Sample Revisions
        revision_count = await self._seed_revisions(db, user_id, plan)
        summary["created"]["revisions"] = revision_count

        await db.commit()

        logger.info("seed_demo_user_complete", summary=summary)
        return summary

    async def _clear_user_data(self, db: AsyncSession, user_id: str):
        """Delete all data for a user."""
        # Order matters due to foreign keys
        await db.execute(delete(PlanRevision).where(PlanRevision.user_id == user_id))
        await db.execute(delete(WorkoutLog).where(WorkoutLog.user_id == user_id))
        await db.execute(delete(AdherenceRecord).where(AdherenceRecord.user_id == user_id))
        await db.execute(delete(WeeklyPlan).where(WeeklyPlan.user_id == user_id))
        await db.execute(delete(WeightEntry).where(WeightEntry.user_id == user_id))
        await db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.flush()
        logger.info("cleared_user_data", user_id=user_id)

    async def _seed_user(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Create the base user account."""
        result = await db.execute(select(User).where(User.id == user_id))
        if result.scalar_one_or_none():
            return None

        user = User(
            id=user_id,
            username=DEMO_USERNAME,
            email="demo@example.com",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        return user

    async def _seed_profile(self, db: AsyncSession, user_id: str) -> Optional[UserProfile]:
        """Create a realistic user profile."""
        result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        if result.scalar_one_or_none():
            return None

        profile = UserProfile(
            user_id=user_id,
            goal="fat_loss",
            equipment=["barbell", "dumbbells", "cables", "bench", "rack"],
            days_per_week=4,
            session_length_min=60,
            preferred_workout_time="morning",
            target_calories=2200,
            target_protein_g=180,
            target_carbs_g=200,
            target_fat_g=75,
            dietary_restrictions=[],
            dietary_preferences=["high_protein", "meal_prep_friendly"],
            injuries=[],
            health_conditions=[],
            height_cm=178.0,
            weight_kg=85.0,
            age=32,
            sex="male",
            body_fat_pct=22.0,
            activity_level="moderate",
            coaching_persona="supportive",
            # Sensitivity settings
            replan_weight_threshold_kg=0.5,
            replan_missed_workout_threshold=2,
            replan_cooldown_days=3,
        )
        db.add(profile)
        await db.flush()
        return profile

    async def _seed_weight_history(self, db: AsyncSession, user_id: str) -> int:
        """Create 14 days of weight history with realistic fluctuation."""
        # Check if we already have entries
        result = await db.execute(
            select(WeightEntry).where(WeightEntry.user_id == user_id).limit(1)
        )
        if result.scalar_one_or_none():
            return 0

        now = datetime.utcnow()
        base_weight = 85.0
        entries = []

        # Create 14 days of history with slight downward trend (fat loss goal)
        weight_data = [
            (14, 85.0, "manual"),
            (13, 85.2, "manual"),
            (12, 84.8, "healthkit"),
            (11, 84.9, "manual"),
            (10, 84.6, "healthkit"),
            (9, 84.7, "manual"),
            (8, 84.4, "healthkit"),
            (7, 84.5, "manual"),  # Week 1 end
            (6, 84.3, "healthkit"),
            (5, 84.4, "manual"),
            (4, 84.1, "healthkit"),
            (3, 84.2, "manual"),
            (2, 83.9, "healthkit"),
            (1, 84.0, "manual"),
            (0, 83.8, "healthkit"),  # Today
        ]

        for days_ago, weight, source in weight_data:
            entry = WeightEntry(
                user_id=user_id,
                weight_kg=weight,
                date=now - timedelta(days=days_ago),
                source=source,
                source_id=f"seed-{days_ago}" if source != "manual" else None,
                synced_at=now if source != "manual" else None,
                notes="Seed data" if days_ago == 14 else None,
            )
            entries.append(entry)

        db.add_all(entries)
        await db.flush()
        return len(entries)

    async def _seed_weekly_plan(self, db: AsyncSession, user_id: str) -> Optional[WeeklyPlan]:
        """Create a sample weekly plan."""
        result = await db.execute(
            select(WeeklyPlan).where(
                WeeklyPlan.user_id == user_id,
                WeeklyPlan.status == "active"
            )
        )
        if result.scalar_one_or_none():
            return None

        now = datetime.utcnow()
        # Find Monday of current week
        days_since_monday = now.weekday()
        week_start = now - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)

        plan = WeeklyPlan(
            id=f"plan-{user_id}-{now.strftime('%Y%m%d')}",
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            status="active",
            workout_plan={
                "days": [
                    {
                        "day": "Monday",
                        "focus": "Upper Body Push",
                        "is_rest_day": False,
                        "exercises": [
                            {"name": "Bench Press", "sets": 4, "reps": "8-10", "weight_kg": 80, "rest_sec": 120},
                            {"name": "Overhead Press", "sets": 3, "reps": "8-10", "weight_kg": 50, "rest_sec": 90},
                            {"name": "Incline Dumbbell Press", "sets": 3, "reps": "10-12", "weight_kg": 30, "rest_sec": 90},
                            {"name": "Tricep Pushdowns", "sets": 3, "reps": "12-15", "weight_kg": 25, "rest_sec": 60},
                            {"name": "Lateral Raises", "sets": 3, "reps": "15-20", "weight_kg": 10, "rest_sec": 60},
                        ],
                        "estimated_duration_min": 55,
                    },
                    {
                        "day": "Tuesday",
                        "focus": "Lower Body",
                        "is_rest_day": False,
                        "exercises": [
                            {"name": "Squat", "sets": 4, "reps": "6-8", "weight_kg": 100, "rest_sec": 180},
                            {"name": "Romanian Deadlift", "sets": 3, "reps": "8-10", "weight_kg": 80, "rest_sec": 120},
                            {"name": "Leg Press", "sets": 3, "reps": "10-12", "weight_kg": 150, "rest_sec": 90},
                            {"name": "Leg Curls", "sets": 3, "reps": "12-15", "weight_kg": 40, "rest_sec": 60},
                            {"name": "Calf Raises", "sets": 4, "reps": "15-20", "weight_kg": 60, "rest_sec": 60},
                        ],
                        "estimated_duration_min": 60,
                    },
                    {
                        "day": "Wednesday",
                        "focus": "Rest",
                        "is_rest_day": True,
                        "exercises": [],
                        "estimated_duration_min": 0,
                    },
                    {
                        "day": "Thursday",
                        "focus": "Upper Body Pull",
                        "is_rest_day": False,
                        "exercises": [
                            {"name": "Barbell Row", "sets": 4, "reps": "6-8", "weight_kg": 70, "rest_sec": 120},
                            {"name": "Pull-ups", "sets": 3, "reps": "8-10", "weight_kg": 0, "rest_sec": 90},
                            {"name": "Cable Rows", "sets": 3, "reps": "10-12", "weight_kg": 60, "rest_sec": 90},
                            {"name": "Face Pulls", "sets": 3, "reps": "15-20", "weight_kg": 20, "rest_sec": 60},
                            {"name": "Barbell Curls", "sets": 3, "reps": "10-12", "weight_kg": 30, "rest_sec": 60},
                        ],
                        "estimated_duration_min": 55,
                    },
                    {
                        "day": "Friday",
                        "focus": "Lower Body",
                        "is_rest_day": False,
                        "exercises": [
                            {"name": "Deadlift", "sets": 4, "reps": "5-6", "weight_kg": 120, "rest_sec": 180},
                            {"name": "Bulgarian Split Squat", "sets": 3, "reps": "8-10", "weight_kg": 20, "rest_sec": 90},
                            {"name": "Hip Thrust", "sets": 3, "reps": "10-12", "weight_kg": 80, "rest_sec": 90},
                            {"name": "Leg Extensions", "sets": 3, "reps": "12-15", "weight_kg": 50, "rest_sec": 60},
                            {"name": "Standing Calf Raises", "sets": 4, "reps": "12-15", "weight_kg": 80, "rest_sec": 60},
                        ],
                        "estimated_duration_min": 60,
                    },
                    {
                        "day": "Saturday",
                        "focus": "Rest",
                        "is_rest_day": True,
                        "exercises": [],
                        "estimated_duration_min": 0,
                    },
                    {
                        "day": "Sunday",
                        "focus": "Rest",
                        "is_rest_day": True,
                        "exercises": [],
                        "estimated_duration_min": 0,
                    },
                ],
                "split_type": "upper_lower",
                "total_training_days": 4,
            },
            meal_plan={
                "days": [
                    self._create_meal_day("Monday", 2200),
                    self._create_meal_day("Tuesday", 2200),
                    self._create_meal_day("Wednesday", 2000),  # Rest day, slightly lower
                    self._create_meal_day("Thursday", 2200),
                    self._create_meal_day("Friday", 2200),
                    self._create_meal_day("Saturday", 2000),
                    self._create_meal_day("Sunday", 2000),
                ],
                "weekly_totals": {
                    "calories": 15000,
                    "protein_g": 1260,
                    "carbs_g": 1400,
                    "fat_g": 525,
                },
            },
            shopping_list=[
                {"item": "Chicken Breast", "quantity": "2 kg", "category": "Protein"},
                {"item": "Eggs", "quantity": "24", "category": "Protein"},
                {"item": "Greek Yogurt", "quantity": "1 kg", "category": "Dairy"},
                {"item": "Rice", "quantity": "1 kg", "category": "Carbs"},
                {"item": "Sweet Potatoes", "quantity": "1 kg", "category": "Carbs"},
                {"item": "Broccoli", "quantity": "500g", "category": "Vegetables"},
                {"item": "Spinach", "quantity": "300g", "category": "Vegetables"},
                {"item": "Olive Oil", "quantity": "500ml", "category": "Fats"},
                {"item": "Almonds", "quantity": "200g", "category": "Fats"},
            ],
            llm_reasoning='{"note": "Seed data - 4-day upper/lower split for fat loss"}',
            rules_applied=["protein_minimum_enforced", "volume_cap_checked"],
        )
        db.add(plan)
        await db.flush()
        return plan

    def _create_meal_day(self, day: str, target_calories: int) -> dict:
        """Create a sample meal day structure."""
        return {
            "day": day,
            "meals": [
                {
                    "meal_type": "breakfast",
                    "name": "Protein Oats",
                    "calories": int(target_calories * 0.25),
                    "protein_g": 35,
                    "carbs_g": 50,
                    "fat_g": 12,
                    "servings": 1.0,
                },
                {
                    "meal_type": "lunch",
                    "name": "Chicken Rice Bowl",
                    "calories": int(target_calories * 0.35),
                    "protein_g": 50,
                    "carbs_g": 60,
                    "fat_g": 15,
                    "servings": 1.0,
                },
                {
                    "meal_type": "dinner",
                    "name": "Salmon with Vegetables",
                    "calories": int(target_calories * 0.30),
                    "protein_g": 45,
                    "carbs_g": 40,
                    "fat_g": 20,
                    "servings": 1.0,
                },
                {
                    "meal_type": "snack_1",
                    "name": "Greek Yogurt with Berries",
                    "calories": int(target_calories * 0.10),
                    "protein_g": 20,
                    "carbs_g": 15,
                    "fat_g": 5,
                    "servings": 1.0,
                },
            ],
            "totals": {
                "calories": target_calories,
                "protein_g": 150,
                "carbs_g": 165,
                "fat_g": 52,
            },
        }

    async def _seed_revisions(
        self,
        db: AsyncSession,
        user_id: str,
        plan: Optional[WeeklyPlan],
    ) -> int:
        """Create sample plan revisions showing different states."""
        if not plan:
            return 0

        # Check if revisions exist
        result = await db.execute(
            select(PlanRevision).where(PlanRevision.plan_id == plan.id).limit(1)
        )
        if result.scalar_one_or_none():
            return 0

        now = datetime.utcnow()
        revisions = [
            # Superseded revision (older)
            PlanRevision(
                plan_id=plan.id,
                user_id=user_id,
                revision_number=1,
                trigger="weight_change",
                target_area="nutrition",
                reason="Initial adjustment: Weight increased 0.8kg, reducing calories by 150",
                patch={"meal_plan": {"calorie_adjust": -150}},
                status="superseded",
                status_reason="Superseded by newer calorie adjustment",
                is_auto_applied=True,
                created_at=now - timedelta(days=5),
            ),
            # Currently active revision
            PlanRevision(
                plan_id=plan.id,
                user_id=user_id,
                revision_number=2,
                trigger="weight_change",
                target_area="nutrition",
                reason="Continued weight gain trend, reducing calories by 200 total",
                patch={"meal_plan": {"calorie_adjust": -200}},
                status="applied",
                is_auto_applied=True,
                created_at=now - timedelta(days=2),
            ),
            # Reverted workout revision
            PlanRevision(
                plan_id=plan.id,
                user_id=user_id,
                revision_number=3,
                trigger="missed_workout",
                target_area="workout",
                reason="2 missed sessions, reducing volume by 15%",
                patch={"workout_plan": {"global_modifier": -0.15}},
                status="reverted",
                status_reason="Reverted by user",
                is_auto_applied=True,
                created_at=now - timedelta(days=1),
            ),
        ]

        db.add_all(revisions)
        await db.flush()
        return len(revisions)

    async def get_demo_user_summary(self, db: AsyncSession, user_id: str = DEMO_USER_ID) -> dict:
        """Get a summary of the demo user's data."""
        from sqlalchemy import func

        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()

        weight_count = await db.execute(
            select(func.count()).select_from(WeightEntry).where(WeightEntry.user_id == user_id)
        )

        plan_result = await db.execute(
            select(WeeklyPlan).where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
        )
        plan = plan_result.scalar_one_or_none()

        revision_count = await db.execute(
            select(func.count()).select_from(PlanRevision).where(PlanRevision.user_id == user_id)
        )

        return {
            "user_id": user_id,
            "has_profile": profile is not None,
            "profile_goal": profile.goal if profile else None,
            "weight_entries": weight_count.scalar() or 0,
            "has_active_plan": plan is not None,
            "plan_id": plan.id if plan else None,
            "revision_count": revision_count.scalar() or 0,
        }
