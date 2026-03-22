"""
Integration tests for critical end-to-end flows.
Tests the full user journey through database operations and services.
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.database import Base
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision, WorkoutLog, AdherenceRecord
from app.services.seed_data import SeedDataService
from app.services.review import WeeklyReviewService


SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

import pytest_asyncio


def create_test_user(user_id: str) -> User:
    """Helper to create a user with required fields."""
    return User(
        id=user_id,
        username=f"user_{user_id[:8]}",
        created_at=datetime.utcnow(),
    )


def create_test_plan(
    user_id: str,
    plan_id: str = None,
    status: str = "active",
    days_ago: int = 0,
    workout_plan: dict = None,
    meal_plan: dict = None,
    shopping_list: list = None,
) -> WeeklyPlan:
    """Helper to create a weekly plan with required fields."""
    now = datetime.utcnow()
    week_start = (now - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

    return WeeklyPlan(
        id=plan_id or f"plan-{uuid4().hex[:8]}",
        user_id=user_id,
        status=status,
        week_start=week_start,
        week_end=week_end,
        workout_plan=workout_plan or {"days": []},
        meal_plan=meal_plan or {"days": []},
        shopping_list=shopping_list or [],
        created_at=now - timedelta(days=days_ago),
    )


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


@pytest_asyncio.fixture
async def review_service():
    return WeeklyReviewService()


# --- Flow 1: User Onboarding → Profile Creation ---

@pytest.mark.asyncio
async def test_full_onboarding_flow(db_session: AsyncSession):
    """Test complete user creation and profile setup."""
    user_id = f"test-user-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    db_session.add(user)

    profile = UserProfile(
        id=f"profile-{user_id}",
        user_id=user_id,
        goal="fat_loss",
        days_per_week=4,
        target_calories=2000,
        target_protein_g=150,
        replan_weight_threshold_kg=0.5,
        replan_missed_workout_threshold=2,
        replan_cooldown_days=3,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(profile)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.id == user_id))
    saved_user = result.scalar_one()
    assert saved_user.id == user_id

    result = await db_session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    saved_profile = result.scalar_one()
    assert saved_profile.goal == "fat_loss"
    assert saved_profile.days_per_week == 4


@pytest.mark.asyncio
async def test_profile_with_sensitivity_settings(db_session: AsyncSession):
    """Verify profile replan sensitivity settings are stored correctly."""
    user_id = f"test-sens-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    profile = UserProfile(
        id=f"profile-{user_id}",
        user_id=user_id,
        goal="muscle_gain",
        days_per_week=5,
        target_calories=3000,
        target_protein_g=200,
        replan_weight_threshold_kg=0.8,
        replan_missed_workout_threshold=3,
        replan_cooldown_days=5,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.add(profile)
    await db_session.commit()

    result = await db_session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    saved = result.scalar_one()
    assert saved.replan_weight_threshold_kg == 0.8
    assert saved.replan_missed_workout_threshold == 3
    assert saved.replan_cooldown_days == 5


# --- Flow 2: Weight Tracking History ---

@pytest.mark.asyncio
async def test_weight_logging_creates_history(db_session: AsyncSession):
    """Test weight entries are stored with proper metadata."""
    user_id = f"test-weight-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    db_session.add(user)

    weights = [
        {"date": datetime.utcnow() - timedelta(days=7), "weight": 85.0, "source": "manual"},
        {"date": datetime.utcnow() - timedelta(days=5), "weight": 84.5, "source": "healthkit"},
        {"date": datetime.utcnow() - timedelta(days=3), "weight": 84.2, "source": "manual"},
        {"date": datetime.utcnow(), "weight": 83.8, "source": "manual"},
    ]

    for w in weights:
        entry = WeightEntry(
            id=f"weight-{uuid4().hex[:8]}",
            user_id=user_id,
            weight_kg=w["weight"],
            date=w["date"],
            source=w["source"],
            created_at=datetime.utcnow(),
        )
        db_session.add(entry)

    await db_session.commit()

    result = await db_session.execute(
        select(WeightEntry).where(WeightEntry.user_id == user_id)
    )
    entries = result.scalars().all()
    assert len(entries) == 4

    sorted_entries = sorted(entries, key=lambda e: e.date)
    assert sorted_entries[-1].weight_kg < sorted_entries[0].weight_kg


@pytest.mark.asyncio
async def test_rolling_average_calculation(db_session: AsyncSession):
    """Test 7-day rolling average calculation from weight entries."""
    user_id = f"test-avg-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    db_session.add(user)

    base_weight = 80.0
    for i in range(10):
        entry = WeightEntry(
            id=f"weight-{uuid4().hex[:8]}",
            user_id=user_id,
            weight_kg=base_weight + (i * 0.1),
            date=datetime.utcnow() - timedelta(days=9 - i),
            source="manual",
            created_at=datetime.utcnow(),
        )
        db_session.add(entry)

    await db_session.commit()

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    result = await db_session.execute(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id)
        .where(WeightEntry.date >= seven_days_ago)
    )
    recent = result.scalars().all()

    avg = sum(e.weight_kg for e in recent) / len(recent)
    assert 80.0 < avg < 81.0


# --- Flow 3: Plan Generation & Storage ---

@pytest.mark.asyncio
async def test_plan_creation_with_full_data(db_session: AsyncSession):
    """Test weekly plan stores all required data fields."""
    user_id = f"test-plan-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    profile = UserProfile(
        id=f"profile-{user_id}",
        user_id=user_id,
        goal="fat_loss",
        days_per_week=4,
        target_calories=2000,
        target_protein_g=150,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.add(profile)

    plan = create_test_plan(
        user_id=user_id,
        workout_plan={
            "days": [
                {"day": 0, "is_rest_day": False, "focus": "Upper Body", "exercises": []},
                {"day": 1, "is_rest_day": True},
                {"day": 2, "is_rest_day": False, "focus": "Lower Body", "exercises": []},
                {"day": 3, "is_rest_day": True},
                {"day": 4, "is_rest_day": False, "focus": "Push", "exercises": []},
                {"day": 5, "is_rest_day": False, "focus": "Pull", "exercises": []},
                {"day": 6, "is_rest_day": True},
            ]
        },
        meal_plan={
            "daily_target_calories": 2000,
            "daily_target_protein_g": 150,
            "days": [{"day": i, "meals": []} for i in range(7)]
        },
        shopping_list=[
            {"name": "Chicken Breast", "quantity": "2 lbs", "category": "Protein"},
            {"name": "Broccoli", "quantity": "1 bunch", "category": "Produce"},
            {"name": "Brown Rice", "quantity": "2 cups", "category": "Grains"},
        ],
    )
    db_session.add(plan)
    await db_session.commit()

    result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.user_id == user_id)
    )
    saved = result.scalar_one()

    assert saved.status == "active"
    assert len(saved.workout_plan["days"]) == 7
    assert len(saved.meal_plan["days"]) == 7
    assert len(saved.shopping_list) == 3


@pytest.mark.asyncio
async def test_plan_status_transitions(db_session: AsyncSession):
    """Test plan status changes when new plan is created."""
    user_id = f"test-transition-{uuid4().hex[:8]}"
    plan1_id = f"plan-old-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    db_session.add(user)

    plan1 = create_test_plan(user_id=user_id, plan_id=plan1_id, days_ago=7)
    db_session.add(plan1)
    await db_session.commit()

    # Re-fetch plan1 to avoid expired state
    result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.id == plan1_id)
    )
    plan1 = result.scalar_one()
    plan1.status = "archived"

    plan2 = create_test_plan(user_id=user_id)
    db_session.add(plan2)
    await db_session.commit()

    result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.id == plan1_id)
    )
    old_plan = result.scalar_one()
    assert old_plan.status == "archived"

    result = await db_session.execute(
        select(WeeklyPlan)
        .where(WeeklyPlan.user_id == user_id)
        .where(WeeklyPlan.status == "active")
    )
    active_plan = result.scalar_one()
    assert active_plan.id != plan1_id


# --- Flow 4: Revision Lifecycle ---

@pytest.mark.asyncio
async def test_revision_creation_and_approval(db_session: AsyncSession):
    """Test revision creation and approval workflow."""
    user_id = f"test-rev-{uuid4().hex[:8]}"
    plan_id = f"plan-{uuid4().hex[:8]}"
    rev_id = f"rev-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    plan = create_test_plan(user_id=user_id, plan_id=plan_id)
    db_session.add(user)
    db_session.add(plan)
    await db_session.commit()

    revision = PlanRevision(
        id=rev_id,
        plan_id=plan_id,
        user_id=user_id,
        trigger="weight_deviation",
        target_area="meal_plan",
        reason="Weight trending up, reducing calories",
        patch={"meal_plan": {"calorie_adjust": -150}},
        status="pending",
        created_at=datetime.utcnow(),
    )
    db_session.add(revision)
    await db_session.commit()

    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.user_id == user_id)
    )
    pending = result.scalar_one()
    assert pending.status == "pending"

    pending.status = "approved"
    pending.status_reason = "User approved calorie reduction"
    await db_session.commit()

    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.id == rev_id)
    )
    approved = result.scalar_one()
    assert approved.status == "approved"
    assert approved.status_reason == "User approved calorie reduction"


@pytest.mark.asyncio
async def test_revision_undo_marks_reverted(db_session: AsyncSession):
    """Test revision undo sets status to reverted."""
    user_id = f"test-undo-{uuid4().hex[:8]}"
    plan_id = f"plan-{uuid4().hex[:8]}"
    rev_id = f"rev-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    plan = create_test_plan(user_id=user_id, plan_id=plan_id)
    db_session.add(user)
    db_session.add(plan)

    revision = PlanRevision(
        id=rev_id,
        plan_id=plan_id,
        user_id=user_id,
        trigger="workout_adherence",
        target_area="workout_plan",
        reason="Missed workouts, reducing volume",
        patch={"workout_plan": {"global_modifier": -0.1}},
        status="applied",
        created_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(revision)
    await db_session.commit()

    # Re-fetch revision to avoid expired state
    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.id == rev_id)
    )
    revision = result.scalar_one()
    revision.status = "reverted"
    revision.status_reason = "User requested undo"
    await db_session.commit()

    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.id == rev_id)
    )
    reverted = result.scalar_one()
    assert reverted.status == "reverted"


@pytest.mark.asyncio
async def test_revision_superseded_by_new_revision(db_session: AsyncSession):
    """Test old revision marked superseded when new one created."""
    user_id = f"test-supersede-{uuid4().hex[:8]}"
    plan_id = f"plan-{uuid4().hex[:8]}"
    rev1_id = f"rev-1-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    plan = create_test_plan(user_id=user_id, plan_id=plan_id)
    db_session.add(user)
    db_session.add(plan)

    rev1 = PlanRevision(
        id=rev1_id,
        plan_id=plan_id,
        user_id=user_id,
        trigger="weight_deviation",
        target_area="meal_plan",
        reason="First adjustment",
        patch={"meal_plan": {"calorie_adjust": -100}},
        status="pending",
        created_at=datetime.utcnow() - timedelta(days=2),
    )
    db_session.add(rev1)
    await db_session.commit()

    # Re-fetch rev1 to avoid expired state
    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.id == rev1_id)
    )
    rev1 = result.scalar_one()
    rev1.status = "superseded"
    rev1.status_reason = "New revision created"

    rev2 = PlanRevision(
        id=f"rev-2-{uuid4().hex[:8]}",
        plan_id=plan_id,
        user_id=user_id,
        trigger="weight_deviation",
        target_area="meal_plan",
        reason="Updated adjustment based on new data",
        patch={"meal_plan": {"calorie_adjust": -200}},
        status="pending",
        created_at=datetime.utcnow(),
    )
    db_session.add(rev2)
    await db_session.commit()

    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.id == rev1_id)
    )
    old = result.scalar_one()
    assert old.status == "superseded"


# --- Flow 5: Workout Logging ---

@pytest.mark.asyncio
async def test_workout_log_creation(db_session: AsyncSession):
    """Test workout logs are stored with all exercise data."""
    user_id = f"test-workout-{uuid4().hex[:8]}"
    plan_id = f"plan-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    plan = create_test_plan(user_id=user_id, plan_id=plan_id)
    db_session.add(user)
    db_session.add(plan)
    await db_session.commit()

    log = WorkoutLog(
        id=f"log-{uuid4().hex[:8]}",
        user_id=user_id,
        plan_id=plan_id,
        date=datetime.utcnow(),
        exercises_completed=[
            {"name": "Squat", "sets": 4, "reps": 8, "weight": 135},
            {"name": "Bench Press", "sets": 3, "reps": 10, "weight": 95},
            {"name": "Deadlift", "sets": 3, "reps": 5, "weight": 185},
        ],
        duration_min=60,
        energy_level=8,
        completion_pct=1.0,
        synced_to_wger="pending",
        created_at=datetime.utcnow(),
    )
    db_session.add(log)
    await db_session.commit()

    result = await db_session.execute(
        select(WorkoutLog).where(WorkoutLog.user_id == user_id)
    )
    saved = result.scalar_one()

    assert saved.duration_min == 60
    assert saved.completion_pct == 1.0
    assert len(saved.exercises_completed) == 3


@pytest.mark.asyncio
async def test_partial_workout_completion(db_session: AsyncSession):
    """Test logging workout with partial completion."""
    user_id = f"test-partial-{uuid4().hex[:8]}"
    plan_id = f"plan-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    plan = create_test_plan(user_id=user_id, plan_id=plan_id)
    db_session.add(user)
    db_session.add(plan)
    await db_session.commit()

    log = WorkoutLog(
        id=f"log-{uuid4().hex[:8]}",
        user_id=user_id,
        plan_id=plan_id,
        date=datetime.utcnow(),
        exercises_completed=[
            {"name": "Squat", "sets": 2, "reps": 8, "weight": 135},
        ],
        duration_min=25,
        energy_level=4,
        completion_pct=0.5,
        synced_to_wger="pending",
        created_at=datetime.utcnow(),
    )
    db_session.add(log)
    await db_session.commit()

    result = await db_session.execute(
        select(WorkoutLog).where(WorkoutLog.user_id == user_id)
    )
    saved = result.scalar_one()
    assert saved.completion_pct == 0.5
    assert saved.energy_level == 4


# --- Flow 6: Adherence Tracking ---

@pytest.mark.asyncio
async def test_adherence_record_creation(db_session: AsyncSession):
    """Test adherence records are properly created."""
    user_id = f"test-adherence-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    db_session.add(user)

    today = datetime.utcnow().date()
    for i in range(7):
        record = AdherenceRecord(
            id=f"adh-{uuid4().hex[:8]}",
            user_id=user_id,
            date=datetime.combine(today - timedelta(days=i), datetime.min.time()),
            workout_planned="true" if i < 5 else "false",
            workout_completed="true" if i < 4 else "false",
            meals_planned=3,
            meals_followed=3 if i < 6 else 2,
            created_at=datetime.utcnow(),
        )
        db_session.add(record)

    await db_session.commit()

    result = await db_session.execute(
        select(AdherenceRecord).where(AdherenceRecord.user_id == user_id)
    )
    records = result.scalars().all()
    assert len(records) == 7

    completed = sum(1 for r in records if r.workout_completed == "true")
    planned = sum(1 for r in records if r.workout_planned == "true")
    rate = completed / planned if planned > 0 else 0
    assert rate == 4 / 5


# --- Flow 7: Review Service Integration ---

@pytest.mark.asyncio
async def test_trends_with_seeded_data(
    db_session: AsyncSession, seed_service, review_service
):
    """Test trends endpoint returns analytics for seeded user."""
    user_id = f"test-trends-{uuid4().hex[:8]}"

    await seed_service.seed_demo_user(db_session, user_id)

    trends = await review_service.generate_trends(db_session, user_id)

    assert trends is not None
    assert trends.trends is not None
    assert trends.goal_alignment is not None
    assert trends.revision_frequency is not None
    assert trends.goal == "fat_loss"


@pytest.mark.asyncio
async def test_weekly_review_returns_data(
    db_session: AsyncSession, seed_service, review_service
):
    """Test weekly review endpoint returns structured data."""
    user_id = f"test-review-{uuid4().hex[:8]}"

    await seed_service.seed_demo_user(db_session, user_id)

    review = await review_service.generate_weekly_review(db_session, user_id, week_offset=0)

    assert review is not None
    assert review.week_start is not None
    assert review.week_end is not None
    assert review.weight is not None
    assert review.workouts is not None
    assert review.nutrition is not None


@pytest.mark.asyncio
async def test_trends_with_insufficient_data(
    db_session: AsyncSession, review_service
):
    """Test trends handles user with minimal data gracefully."""
    user_id = f"test-sparse-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    profile = UserProfile(
        id=f"profile-{user_id}",
        user_id=user_id,
        goal="maintenance",
        days_per_week=3,
        target_calories=2200,
        target_protein_g=130,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.add(profile)
    await db_session.commit()

    trends = await review_service.generate_trends(db_session, user_id)

    assert trends is not None
    assert trends.goal == "maintenance"
    assert trends.trends.weight.direction == "insufficient_data"


# --- Flow 8: Multi-Week History Tracking ---

@pytest.mark.asyncio
async def test_multi_week_weight_trend(db_session: AsyncSession):
    """Test weight tracking across 4 weeks for trends."""
    user_id = f"test-4week-{uuid4().hex[:8]}"

    user = create_test_user(user_id)
    profile = UserProfile(
        id=f"profile-{user_id}",
        user_id=user_id,
        goal="fat_loss",
        days_per_week=4,
        target_calories=2000,
        target_protein_g=150,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.add(profile)

    base_weight = 85.0
    for week in range(4):
        for day in range(3):
            days_ago = (3 - week) * 7 + (2 - day)
            entry = WeightEntry(
                id=f"weight-{uuid4().hex[:8]}",
                user_id=user_id,
                weight_kg=base_weight - (week * 0.5) - (day * 0.1),
                date=datetime.utcnow() - timedelta(days=days_ago),
                source="manual",
                created_at=datetime.utcnow(),
            )
            db_session.add(entry)

    await db_session.commit()

    result = await db_session.execute(
        select(WeightEntry).where(WeightEntry.user_id == user_id)
    )
    entries = result.scalars().all()
    assert len(entries) == 12

    sorted_entries = sorted(entries, key=lambda e: e.date)
    first_week_avg = sum(e.weight_kg for e in sorted_entries[:3]) / 3
    last_week_avg = sum(e.weight_kg for e in sorted_entries[-3:]) / 3
    assert last_week_avg < first_week_avg


# --- Flow 9: Seed Data Roundtrip ---

@pytest.mark.asyncio
async def test_seed_creates_complete_user_data(
    db_session: AsyncSession, seed_service
):
    """Verify seed creates all related data for a user."""
    user_id = f"test-seed-full-{uuid4().hex[:8]}"

    summary = await seed_service.seed_demo_user(db_session, user_id)

    assert summary["user_id"] == user_id
    assert summary["created"]["user"] is True
    assert summary["created"]["profile"] is True
    assert summary["created"]["weight_entries"] > 0
    assert summary["created"]["plan"] is not None
    assert summary["created"]["revisions"] > 0

    result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.user_id == user_id)
    )
    plan = result.scalar_one()

    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.plan_id == plan.id)
    )
    revisions = result.scalars().all()
    assert len(revisions) == summary["created"]["revisions"]
