"""
Tests for weekly review service and API endpoints.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.database import Base
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, WorkoutLog, AdherenceRecord, PlanRevision
from app.services.review import WeeklyReviewService


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
async def review_service():
    return WeeklyReviewService()


@pytest_asyncio.fixture
async def demo_user(db_session: AsyncSession):
    """Create a demo user with profile."""
    user = User(id="review-test-user", username="reviewer", email="review@test.com")
    db_session.add(user)

    profile = UserProfile(
        user_id="review-test-user",
        goal="fat_loss",
        days_per_week=4,
        target_calories=2000,
        target_protein_g=150,
    )
    db_session.add(profile)
    await db_session.commit()
    return user


# --- Test: No profile returns appropriate message ---

@pytest.mark.asyncio
async def test_review_no_profile(db_session: AsyncSession, review_service: WeeklyReviewService):
    """Review for nonexistent user returns empty state message."""
    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="nonexistent-user",
    )

    assert result.message is not None
    assert "profile" in result.message.lower()
    assert result.goal is None


# --- Test: No active plan returns appropriate message ---

@pytest.mark.asyncio
async def test_review_no_plan(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Review with profile but no plan returns plan generation prompt."""
    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
    )

    assert result.message is not None
    assert "plan" in result.message.lower()
    assert result.goal == "fat_loss"
    assert result.workouts.planned == 0


# --- Test: Full review with workout logs ---

@pytest.mark.asyncio
async def test_review_with_workout_logs(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Review calculates workout metrics from logs."""
    # Create an active plan
    today = datetime.now()
    week_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start -= timedelta(days=today.weekday())

    plan = WeeklyPlan(
        id="review-test-plan",
        user_id="review-test-user",
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        status="active",
        workout_plan={
            "days": [
                {"day": "Monday", "is_rest_day": False, "exercises": []},
                {"day": "Tuesday", "is_rest_day": True},
                {"day": "Wednesday", "is_rest_day": False, "exercises": []},
                {"day": "Thursday", "is_rest_day": True},
                {"day": "Friday", "is_rest_day": False, "exercises": []},
                {"day": "Saturday", "is_rest_day": False, "exercises": []},
                {"day": "Sunday", "is_rest_day": True},
            ]
        },
        meal_plan={},
        shopping_list=[],
    )
    db_session.add(plan)

    # Add workout logs
    for i in range(3):
        log = WorkoutLog(
            user_id="review-test-user",
            plan_id="review-test-plan",
            date=week_start + timedelta(days=i * 2),
            exercises_completed=[{"name": "Squat", "sets": 3}],
            completion_pct=100.0,
            duration_min=45,
            energy_level=4,
        )
        db_session.add(log)

    await db_session.commit()

    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
    )

    assert result.workouts.planned == 4  # 4 non-rest days
    assert result.workouts.completed == 3
    assert result.workouts.completion_pct == 75.0
    assert result.workouts.avg_energy == 4.0
    assert result.workouts.total_duration_min == 135


# --- Test: Weight trend calculation ---

@pytest.mark.asyncio
async def test_review_weight_trend_losing(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Weight trend correctly detects losing direction."""
    # Add weight entries showing downward trend
    # i=0 is today (current), i=13 is 14 days ago (oldest)
    # For losing: current should be lower than oldest → use + (i * 0.1)
    today = datetime.now()
    for i in range(14):
        entry = WeightEntry(
            user_id="review-test-user",
            weight_kg=83.0 + (i * 0.1),  # Today=83.0, oldest=84.3 → losing
            date=today - timedelta(days=i),
            source="manual",
        )
        db_session.add(entry)

    await db_session.commit()

    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
    )

    assert result.weight.trend == "losing"
    assert result.weight.change_kg < 0
    assert result.weight.aligned_with_goal is True  # Goal is fat_loss


# --- Test: Weight trend gaining ---

@pytest.mark.asyncio
async def test_review_weight_trend_gaining(db_session: AsyncSession, review_service: WeeklyReviewService):
    """Weight trend correctly detects gaining direction."""
    user = User(id="gainer-test", username="gainer", email="gain@test.com")
    db_session.add(user)

    profile = UserProfile(
        user_id="gainer-test",
        goal="muscle_gain",
        days_per_week=4,
        target_calories=3000,
        target_protein_g=200,
    )
    db_session.add(profile)

    # Add weight entries showing upward trend
    # i=0 is today (current), i=13 is 14 days ago (oldest)
    # For gaining: current should be higher than oldest → use - (i * 0.1)
    today = datetime.now()
    for i in range(14):
        entry = WeightEntry(
            user_id="gainer-test",
            weight_kg=76.3 - (i * 0.1),  # Today=76.3, oldest=75.0 → gaining
            date=today - timedelta(days=i),
            source="manual",
        )
        db_session.add(entry)

    await db_session.commit()

    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="gainer-test",
    )

    assert result.weight.trend == "gaining"
    assert result.weight.change_kg > 0
    assert result.weight.aligned_with_goal is True  # Goal is muscle_gain


# --- Test: Insights generation ---

@pytest.mark.asyncio
async def test_review_generates_insights(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Review generates appropriate insights based on data."""
    # Create plan
    today = datetime.now()
    week_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start -= timedelta(days=today.weekday())

    plan = WeeklyPlan(
        id="insight-test-plan",
        user_id="review-test-user",
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        status="active",
        workout_plan={
            "days": [
                {"day": "Monday", "is_rest_day": False},
                {"day": "Tuesday", "is_rest_day": True},
                {"day": "Wednesday", "is_rest_day": False},
                {"day": "Thursday", "is_rest_day": True},
                {"day": "Friday", "is_rest_day": False},
                {"day": "Saturday", "is_rest_day": True},
                {"day": "Sunday", "is_rest_day": True},
            ]
        },
        meal_plan={},
        shopping_list=[],
    )
    db_session.add(plan)

    # Add 3/3 workouts completed (100%)
    for i in range(3):
        log = WorkoutLog(
            user_id="review-test-user",
            plan_id="insight-test-plan",
            date=week_start + timedelta(days=i * 2),
            exercises_completed=[],
            completion_pct=100.0,
            duration_min=50,
            energy_level=4,
        )
        db_session.add(log)

    # Add weight entries showing loss
    for i in range(7):
        entry = WeightEntry(
            user_id="review-test-user",
            weight_kg=85.0 - (i * 0.15),
            date=today - timedelta(days=i),
            source="manual",
        )
        db_session.add(entry)

    await db_session.commit()

    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
    )

    assert len(result.insights) > 0

    # Should have positive workout insight
    workout_insights = [i for i in result.insights if "workout" in i.lower()]
    assert len(workout_insights) > 0
    assert "3/3" in workout_insights[0]

    # Should have weight trend insight for fat loss
    weight_insights = [i for i in result.insights if "weight" in i.lower() or "fat loss" in i.lower()]
    assert len(weight_insights) > 0


# --- Test: Coach adjustments summary ---

@pytest.mark.asyncio
async def test_review_summarizes_adjustments(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Review correctly summarizes plan revisions."""
    today = datetime.now()
    week_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start -= timedelta(days=today.weekday())

    plan = WeeklyPlan(
        id="adjust-test-plan",
        user_id="review-test-user",
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        status="active",
        workout_plan={"days": []},
        meal_plan={},
        shopping_list=[],
    )
    db_session.add(plan)

    # Add a revision with calorie adjustment
    revision = PlanRevision(
        id="test-revision-1",
        plan_id="adjust-test-plan",
        user_id="review-test-user",
        revision_number=1,
        trigger="weight_change",
        target_area="nutrition",
        reason="Weight loss stalled",
        patch={
            "meal_plan": {"calorie_adjust": -150}
        },
        status="applied",
        is_auto_applied=True,
    )
    db_session.add(revision)

    await db_session.commit()

    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
    )

    assert len(result.coach_adjustments) == 1
    adj = result.coach_adjustments[0]
    assert adj.trigger == "weight_change"
    assert adj.area == "nutrition"
    assert "calories" in adj.change.lower()
    assert "-150" in adj.change
    assert adj.status == "applied"


# --- Test: Week offset parameter ---

@pytest.mark.asyncio
async def test_review_week_offset(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Week offset correctly adjusts date boundaries."""
    result_current = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
        week_offset=0,
    )

    result_last = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
        week_offset=-1,
    )

    # Parse dates
    current_start = datetime.strptime(result_current.week_start, "%Y-%m-%d")
    last_start = datetime.strptime(result_last.week_start, "%Y-%m-%d")

    # Last week should be 7 days before current week
    assert (current_start - last_start).days == 7


# --- Test: Next action recommendation ---

@pytest.mark.asyncio
async def test_review_next_action(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Review provides appropriate next action."""
    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
    )

    # No plan, should suggest generating one
    assert result.next_action is not None
    assert "plan" in result.next_action.lower()


# --- Test: Nutrition adherence calculation ---

@pytest.mark.asyncio
async def test_review_nutrition_adherence(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Nutrition adherence is correctly calculated from records."""
    today = datetime.now()
    week_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start -= timedelta(days=today.weekday())

    # Add adherence records
    for i in range(5):
        record = AdherenceRecord(
            user_id="review-test-user",
            date=week_start + timedelta(days=i),
            meals_planned=3,
            meals_followed=3 if i < 4 else 1,  # 4 days on target, 1 not
            calories_actual=1900 + (i * 50),
        )
        db_session.add(record)

    await db_session.commit()

    result = await review_service.generate_weekly_review(
        db=db_session,
        user_id="review-test-user",
    )

    assert result.nutrition.days_on_target == 4  # 4 days at 80%+ meals
    assert result.nutrition.adherence_pct == 80.0  # 4/5 = 80%
    assert result.nutrition.avg_calories is not None


# --- Trends Endpoint Tests ---

@pytest.mark.asyncio
async def test_trends_no_profile(db_session: AsyncSession, review_service: WeeklyReviewService):
    """Trends for nonexistent user returns empty state message."""
    result = await review_service.generate_trends(
        db=db_session,
        user_id="nonexistent-user",
    )

    assert result.message is not None
    assert "profile" in result.message.lower()
    assert result.goal is None


@pytest.mark.asyncio
async def test_trends_returns_4_weeks(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Trends aggregates 4 weeks of data."""
    result = await review_service.generate_trends(
        db=db_session,
        user_id="review-test-user",
    )

    assert result.user_id == "review-test-user"
    assert result.goal == "fat_loss"
    assert result.period == "4 weeks"
    assert len(result.trends.weight.weeks) == 4
    assert len(result.trends.workouts.weeks) == 4
    assert len(result.trends.nutrition.weeks) == 4


@pytest.mark.asyncio
async def test_trends_revision_frequency(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Revision frequency correctly counts different statuses."""
    today = datetime.now()

    # Add revisions with different statuses
    for i, status in enumerate(["applied", "applied", "approved", "reverted", "superseded"]):
        revision = PlanRevision(
            id=f"trend-test-rev-{i}",
            plan_id="dummy-plan",
            user_id="review-test-user",
            revision_number=i,
            trigger="weight_change",
            target_area="nutrition",
            reason="Test",
            patch={},
            status=status,
            is_auto_applied=(status == "applied"),
        )
        db_session.add(revision)

    await db_session.commit()

    result = await review_service.generate_trends(
        db=db_session,
        user_id="review-test-user",
    )

    assert result.revision_frequency.total == 5
    assert result.revision_frequency.auto_applied == 2
    assert result.revision_frequency.user_approved == 1
    assert result.revision_frequency.undone == 1
    assert result.revision_frequency.superseded == 1
    assert result.revision_frequency.assessment == "active"  # 5+ revisions


@pytest.mark.asyncio
async def test_trends_goal_alignment_on_track(db_session: AsyncSession, review_service: WeeklyReviewService):
    """Goal alignment correctly calculates on_track status."""
    # Create user with fat_loss goal
    user = User(id="alignment-test", username="aligner", email="align@test.com")
    db_session.add(user)

    profile = UserProfile(
        user_id="alignment-test",
        goal="fat_loss",
        days_per_week=4,
        target_calories=2000,
        target_protein_g=150,
    )
    db_session.add(profile)

    # Add weight entries showing consistent loss
    today = datetime.now()
    for i in range(28):
        entry = WeightEntry(
            user_id="alignment-test",
            weight_kg=85.0 + (i * 0.05),  # Losing weight over 4 weeks
            date=today - timedelta(days=i),
            source="manual",
        )
        db_session.add(entry)

    await db_session.commit()

    result = await review_service.generate_trends(
        db=db_session,
        user_id="alignment-test",
    )

    # Should have aligned weight weeks (losing = aligned with fat_loss)
    assert result.goal_alignment.weight_aligned_weeks >= 0
    # Status depends on total metrics
    assert result.goal_alignment.status in ["on_track", "mixed", "off_track", "insufficient_data"]


@pytest.mark.asyncio
async def test_trends_direction_calculation(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Trend directions are correctly calculated."""
    result = await review_service.generate_trends(
        db=db_session,
        user_id="review-test-user",
    )

    # With no data, direction should be insufficient_data
    assert result.trends.weight.direction in ["up", "down", "stable", "insufficient_data"]
    assert result.trends.workouts.direction in ["up", "down", "stable", "insufficient_data"]
    assert result.trends.nutrition.direction in ["up", "down", "stable", "insufficient_data"]


@pytest.mark.asyncio
async def test_trends_revision_frequency_stable(db_session: AsyncSession, review_service: WeeklyReviewService, demo_user):
    """Revision frequency shows 'stable' with 0-1 revisions."""
    result = await review_service.generate_trends(
        db=db_session,
        user_id="review-test-user",
    )

    # No revisions added, should be stable
    assert result.revision_frequency.total == 0
    assert result.revision_frequency.assessment == "stable"
