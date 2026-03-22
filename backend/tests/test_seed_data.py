"""
Tests for seed data service and admin endpoints.
"""
import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func

from app.database import Base
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision
from app.services.seed_data import SeedDataService, DEMO_USER_ID


SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


import pytest_asyncio


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(
        autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
    )
    async with SessionLocal() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seed_service():
    return SeedDataService()


@pytest.mark.asyncio
async def test_seed_creates_demo_user(db_session: AsyncSession, seed_service: SeedDataService):
    """Verify seed creates a complete demo user."""
    summary = await seed_service.seed_demo_user(db_session, DEMO_USER_ID)

    assert summary["user_id"] == DEMO_USER_ID
    assert summary["created"]["user"] is True
    assert summary["created"]["profile"] is True
    assert summary["created"]["weight_entries"] == 15  # 14 days + today
    assert summary["created"]["plan"] is not None
    assert summary["created"]["revisions"] == 3


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session: AsyncSession, seed_service: SeedDataService):
    """Verify calling seed multiple times doesn't duplicate data."""
    # First call
    summary1 = await seed_service.seed_demo_user(db_session, DEMO_USER_ID)
    assert summary1["created"]["user"] is True

    # Second call - should skip
    summary2 = await seed_service.seed_demo_user(db_session, DEMO_USER_ID)
    assert summary2["skipped"]["user"] == "already exists"
    assert summary2["skipped"]["profile"] == "already exists"
    assert summary2["created"]["weight_entries"] == 0

    # Verify only one user exists
    result = await db_session.execute(
        select(func.count()).select_from(User).where(User.id == DEMO_USER_ID)
    )
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_seed_clear_existing_resets_data(db_session: AsyncSession, seed_service: SeedDataService):
    """Verify clear_existing=True removes and recreates data."""
    # First seed
    await seed_service.seed_demo_user(db_session, DEMO_USER_ID)

    # Get initial plan ID
    result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.user_id == DEMO_USER_ID)
    )
    initial_plan = result.scalar_one()
    initial_plan_id = initial_plan.id

    # Re-seed with clear
    summary = await seed_service.seed_demo_user(
        db_session, DEMO_USER_ID, clear_existing=True
    )

    assert summary["created"]["user"] is True
    assert summary["created"]["plan"] is not None

    # New plan should have different timestamp in ID
    result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.user_id == DEMO_USER_ID)
    )
    new_plan = result.scalar_one()
    # Plan ID format: plan-{user_id}-{timestamp}
    assert new_plan.id == summary["created"]["plan"]


@pytest.mark.asyncio
async def test_seed_creates_profile_with_sensitivity_settings(
    db_session: AsyncSession, seed_service: SeedDataService
):
    """Verify seeded profile has replan sensitivity settings."""
    await seed_service.seed_demo_user(db_session, DEMO_USER_ID)

    result = await db_session.execute(
        select(UserProfile).where(UserProfile.user_id == DEMO_USER_ID)
    )
    profile = result.scalar_one()

    assert profile.replan_weight_threshold_kg == 0.5
    assert profile.replan_missed_workout_threshold == 2
    assert profile.replan_cooldown_days == 3
    assert profile.goal == "fat_loss"
    assert profile.days_per_week == 4


@pytest.mark.asyncio
async def test_seed_creates_weight_history_with_sources(
    db_session: AsyncSession, seed_service: SeedDataService
):
    """Verify weight history includes mixed sources."""
    await seed_service.seed_demo_user(db_session, DEMO_USER_ID)

    result = await db_session.execute(
        select(WeightEntry).where(WeightEntry.user_id == DEMO_USER_ID)
    )
    entries = result.scalars().all()

    sources = set(e.source for e in entries)
    assert "manual" in sources
    assert "healthkit" in sources

    # Verify trend is downward (fat loss goal)
    oldest = min(entries, key=lambda e: e.date)
    newest = max(entries, key=lambda e: e.date)
    assert newest.weight_kg < oldest.weight_kg


@pytest.mark.asyncio
async def test_seed_creates_plan_with_workout_and_meals(
    db_session: AsyncSession, seed_service: SeedDataService
):
    """Verify plan includes workout and meal data."""
    await seed_service.seed_demo_user(db_session, DEMO_USER_ID)

    result = await db_session.execute(
        select(WeeklyPlan).where(
            WeeklyPlan.user_id == DEMO_USER_ID,
            WeeklyPlan.status == "active"
        )
    )
    plan = result.scalar_one()

    # Workout plan
    assert "days" in plan.workout_plan
    assert len(plan.workout_plan["days"]) == 7
    workout_days = [d for d in plan.workout_plan["days"] if not d.get("is_rest_day")]
    assert len(workout_days) == 4  # 4-day split

    # Meal plan
    assert "days" in plan.meal_plan
    assert len(plan.meal_plan["days"]) == 7

    # Shopping list
    assert len(plan.shopping_list) > 0


@pytest.mark.asyncio
async def test_seed_creates_revisions_with_different_statuses(
    db_session: AsyncSession, seed_service: SeedDataService
):
    """Verify revisions include superseded, applied, and reverted states."""
    await seed_service.seed_demo_user(db_session, DEMO_USER_ID)

    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.user_id == DEMO_USER_ID)
    )
    revisions = result.scalars().all()

    statuses = set(r.status for r in revisions)
    assert "superseded" in statuses
    assert "applied" in statuses
    assert "reverted" in statuses


@pytest.mark.asyncio
async def test_get_demo_user_summary(db_session: AsyncSession, seed_service: SeedDataService):
    """Verify summary endpoint returns correct counts."""
    await seed_service.seed_demo_user(db_session, DEMO_USER_ID)

    summary = await seed_service.get_demo_user_summary(db_session, DEMO_USER_ID)

    assert summary["user_id"] == DEMO_USER_ID
    assert summary["has_profile"] is True
    assert summary["profile_goal"] == "fat_loss"
    assert summary["weight_entries"] == 15
    assert summary["has_active_plan"] is True
    assert summary["plan_id"] is not None
    assert summary["revision_count"] == 3


@pytest.mark.asyncio
async def test_get_demo_user_summary_nonexistent(
    db_session: AsyncSession, seed_service: SeedDataService
):
    """Verify summary for non-existent user returns empty values."""
    summary = await seed_service.get_demo_user_summary(db_session, "nonexistent-user")

    assert summary["user_id"] == "nonexistent-user"
    assert summary["has_profile"] is False
    assert summary["profile_goal"] is None
    assert summary["weight_entries"] == 0
    assert summary["has_active_plan"] is False
    assert summary["plan_id"] is None
    assert summary["revision_count"] == 0


@pytest.mark.asyncio
async def test_custom_user_id(db_session: AsyncSession, seed_service: SeedDataService):
    """Verify seed works with custom user ID."""
    custom_id = "custom-test-user-123"
    summary = await seed_service.seed_demo_user(db_session, custom_id)

    assert summary["user_id"] == custom_id
    assert summary["created"]["user"] is True

    result = await db_session.execute(select(User).where(User.id == custom_id))
    user = result.scalar_one()
    assert user.id == custom_id


# --- Audit Bundle Export Tests ---

from app.api.admin import _serialize_datetime


def test_serialize_datetime_handles_nested_structures():
    """Verify datetime serialization handles nested dicts and lists."""
    test_data = {
        "simple_date": datetime(2024, 1, 15, 10, 30, 0),
        "nested": {
            "date": datetime(2024, 1, 16, 11, 0, 0),
            "list_of_dates": [
                datetime(2024, 1, 17, 12, 0, 0),
                datetime(2024, 1, 18, 13, 0, 0),
            ],
        },
        "regular_value": "hello",
        "number": 42,
    }

    result = _serialize_datetime(test_data)

    assert result["simple_date"] == "2024-01-15T10:30:00"
    assert result["nested"]["date"] == "2024-01-16T11:00:00"
    assert result["nested"]["list_of_dates"][0] == "2024-01-17T12:00:00"
    assert result["regular_value"] == "hello"
    assert result["number"] == 42
