"""
Tests for Weight Sync v1

Verifies:
- Duplicate syncs do not stack
- Synced + manual entries coexist correctly
- Threshold/cooldown prevent overreaction
- Synced entry can trigger replan only through normal evaluator
- Superseded/reverted revision state handling still works after sync-triggered replans
"""
import pytest
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database import Base
from app.models.user import UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision
from app.services.weight_sync import WeightSyncService, DEDUPE_WINDOW_MINUTES, DEDUPE_WEIGHT_TOLERANCE_KG

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

import pytest_asyncio


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
    async with SessionLocal() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
def weight_sync_service():
    return WeightSyncService()


# --- Test: Duplicate syncs do not stack ---

@pytest.mark.asyncio
async def test_duplicate_sync_by_source_id_ignored(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Syncing the same source_id twice should deduplicate.
    """
    user = UserProfile(user_id="test_dup", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    # First sync
    status1, entry1, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_dup",
        weight_kg=80.0,
        source="healthkit",
        source_id="hk-12345",
    )
    await db_session.flush()  # Get ID without expiring

    assert status1 == "created"
    assert entry1 is not None
    entry1_id = entry1.id
    assert entry1.source == "healthkit"
    assert entry1.source_id == "hk-12345"

    await db_session.commit()

    # Second sync with same source_id
    status2, entry2, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_dup",
        weight_kg=80.0,
        source="healthkit",
        source_id="hk-12345",
    )

    assert status2 == "deduplicated"
    assert entry2.id == entry1_id  # Same entry returned


@pytest.mark.asyncio
async def test_duplicate_sync_near_identical_ignored(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Syncing near-identical entries (same source, similar time/weight) should deduplicate.
    """
    user = UserProfile(user_id="test_near", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # First sync
    status1, entry1, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_near",
        weight_kg=75.5,
        source="google_fit",
        measured_at=now,
    )
    await db_session.commit()

    assert status1 == "created"

    # Second sync within time window and weight tolerance
    status2, entry2, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_near",
        weight_kg=75.55,  # Within tolerance
        source="google_fit",
        measured_at=now + datetime.timedelta(minutes=2),  # Within window
    )

    assert status2 == "deduplicated"
    assert entry2.id == entry1.id


@pytest.mark.asyncio
async def test_different_sources_not_deduplicated(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Same weight from different sources should NOT be deduplicated.
    """
    user = UserProfile(user_id="test_diff_src", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # Sync from HealthKit
    status1, entry1, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_diff_src",
        weight_kg=82.0,
        source="healthkit",
        measured_at=now,
    )
    await db_session.flush()
    entry1_id = entry1.id
    await db_session.commit()

    # Sync same weight from Google Fit
    status2, entry2, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_diff_src",
        weight_kg=82.0,
        source="google_fit",
        measured_at=now,
    )
    await db_session.flush()
    entry2_id = entry2.id
    await db_session.commit()

    assert status1 == "created"
    assert status2 == "created"
    assert entry1_id != entry2_id


# --- Test: Synced + manual entries coexist correctly ---

@pytest.mark.asyncio
async def test_synced_and_manual_entries_coexist(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Manual and synced entries should coexist in the same history.
    """
    user = UserProfile(user_id="test_coexist", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # Manual entry
    manual_entry = WeightEntry(
        user_id="test_coexist",
        weight_kg=78.0,
        source="manual",
        date=now - datetime.timedelta(hours=1),
    )
    db_session.add(manual_entry)
    await db_session.commit()

    # Synced entry
    status, synced_entry, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_coexist",
        weight_kg=78.2,
        source="healthkit",
        measured_at=now,
    )
    await db_session.commit()

    assert status == "created"

    # Get latest - should be the synced one
    latest = await weight_sync_service.get_latest_weight(db_session, "test_coexist")

    assert latest is not None
    assert latest["weight_kg"] == 78.2
    assert latest["source"] == "healthkit"
    assert latest["trend"] == "up"  # 78.0 -> 78.2
    assert latest["delta_kg"] == 0.2


@pytest.mark.asyncio
async def test_manual_entry_not_deduplicated_with_sync(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Manual entries should never be deduplicated against synced entries.
    """
    user = UserProfile(user_id="test_manual_sync", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # Synced entry
    status1, entry1, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_manual_sync",
        weight_kg=85.0,
        source="healthkit",
        measured_at=now,
    )
    await db_session.commit()

    # Manual entry at same time and weight
    manual_entry = WeightEntry(
        user_id="test_manual_sync",
        weight_kg=85.0,
        source="manual",
        date=now,
    )
    db_session.add(manual_entry)
    await db_session.commit()

    # Both should exist
    from sqlalchemy import select
    result = await db_session.execute(
        select(WeightEntry).where(WeightEntry.user_id == "test_manual_sync")
    )
    entries = result.scalars().all()

    assert len(entries) == 2
    sources = {e.source for e in entries}
    assert sources == {"healthkit", "manual"}


# --- Test: Threshold/cooldown prevent overreaction ---

@pytest.mark.asyncio
async def test_threshold_prevents_replan(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Weight change below threshold should NOT trigger replan.
    """
    user = UserProfile(
        user_id="test_threshold",
        target_calories=2000,
        target_protein_g=150,
        replan_weight_threshold_kg=0.5,  # 0.5kg threshold
    )
    db_session.add(user)

    plan = WeeklyPlan(
        id="plan_threshold",
        user_id="test_threshold",
        week_start=datetime.datetime.utcnow(),
        week_end=datetime.datetime.utcnow() + datetime.timedelta(days=7),
        status="active",
        workout_plan={},
        meal_plan={},
    )
    db_session.add(plan)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # First weight entry
    await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_threshold",
        weight_kg=80.0,
        source="healthkit",
        measured_at=now - datetime.timedelta(days=1),
    )
    await db_session.commit()

    # Second entry with small change (below threshold)
    status, _, replan_triggered, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_threshold",
        weight_kg=80.3,  # +0.3kg, below 0.5kg threshold
        source="healthkit",
        measured_at=now,
    )
    await db_session.commit()

    assert status == "created"
    assert replan_triggered is False


@pytest.mark.asyncio
async def test_cooldown_prevents_replan(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Recent revision should prevent new replan due to cooldown.
    """
    user = UserProfile(
        user_id="test_cooldown",
        target_calories=2000,
        target_protein_g=150,
        replan_weight_threshold_kg=0.5,
        replan_cooldown_days=3,
    )
    db_session.add(user)

    plan = WeeklyPlan(
        id="plan_cooldown",
        user_id="test_cooldown",
        week_start=datetime.datetime.utcnow(),
        week_end=datetime.datetime.utcnow() + datetime.timedelta(days=7),
        status="active",
        workout_plan={},
        meal_plan={},
    )
    db_session.add(plan)

    # Recent revision (within cooldown)
    recent_revision = PlanRevision(
        plan_id="plan_cooldown",
        user_id="test_cooldown",
        target_area="nutrition",
        trigger="weight_change",
        reason="Previous adjustment",
        patch={"meal_plan": {"calorie_adjust": -100}},
        status="applied",
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=1),  # 1 day ago
    )
    db_session.add(recent_revision)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # First weight entry
    await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_cooldown",
        weight_kg=80.0,
        source="healthkit",
        measured_at=now - datetime.timedelta(days=1),
    )
    await db_session.commit()

    # Second entry with significant change
    status, _, replan_triggered, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_cooldown",
        weight_kg=81.0,  # +1.0kg, above threshold
        source="healthkit",
        measured_at=now,
    )
    await db_session.commit()

    assert status == "created"
    assert replan_triggered is False  # Blocked by cooldown


# --- Test: Synced entry can trigger replan only through normal evaluator ---

@pytest.mark.asyncio
async def test_sync_triggers_replan_through_evaluator(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Synced weight above threshold (and outside cooldown) should trigger replan.
    """
    user = UserProfile(
        user_id="test_trigger",
        target_calories=2000,
        target_protein_g=150,
        goal="fat_loss",
        replan_weight_threshold_kg=0.5,
        replan_cooldown_days=3,
    )
    db_session.add(user)

    plan = WeeklyPlan(
        id="plan_trigger",
        user_id="test_trigger",
        week_start=datetime.datetime.utcnow(),
        week_end=datetime.datetime.utcnow() + datetime.timedelta(days=7),
        status="active",
        workout_plan={},
        meal_plan={"days": []},
    )
    db_session.add(plan)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # First weight entry
    await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_trigger",
        weight_kg=80.0,
        source="healthkit",
        measured_at=now - datetime.timedelta(days=5),
    )
    await db_session.commit()

    # Second entry with significant change (above threshold, outside cooldown)
    status, _, replan_triggered, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_trigger",
        weight_kg=81.0,  # +1.0kg, above 0.5kg threshold
        source="healthkit",
        measured_at=now,
    )
    await db_session.commit()

    assert status == "created"
    assert replan_triggered is True


# --- Test: Revision state handling after sync-triggered replans ---

@pytest.mark.asyncio
async def test_sync_replan_respects_supersession(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Sync-triggered replan should supersede prior nutrition revisions.
    """
    from app.api.planning import _supersede_active_revisions

    user = UserProfile(
        user_id="test_supersede",
        target_calories=2000,
        target_protein_g=150,
    )
    db_session.add(user)

    plan = WeeklyPlan(
        id="plan_supersede",
        user_id="test_supersede",
        week_start=datetime.datetime.utcnow(),
        week_end=datetime.datetime.utcnow() + datetime.timedelta(days=7),
        status="active",
        workout_plan={},
        meal_plan={},
    )
    db_session.add(plan)

    # Existing active revision
    existing_rev = PlanRevision(
        id="rev_existing",
        plan_id="plan_supersede",
        user_id="test_supersede",
        target_area="nutrition",
        trigger="weight_change",
        reason="Previous adjustment",
        patch={"meal_plan": {"calorie_adjust": -100}},
        status="applied",
    )
    db_session.add(existing_rev)
    await db_session.commit()

    # Simulate new revision from sync-triggered replan
    count = await _supersede_active_revisions(
        db_session,
        "plan_supersede",
        "nutrition",
        "rev_new",
        "weight_change",
    )
    await db_session.commit()

    await db_session.refresh(existing_rev)

    assert count == 1
    assert existing_rev.status == "superseded"


@pytest.mark.asyncio
async def test_get_latest_weight_with_sync_metadata(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    get_latest_weight should return full sync metadata.
    """
    user = UserProfile(user_id="test_latest", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # Add entries
    manual_entry = WeightEntry(
        user_id="test_latest",
        weight_kg=77.0,
        source="manual",
        date=now - datetime.timedelta(hours=2),
    )
    db_session.add(manual_entry)
    await db_session.commit()

    await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_latest",
        weight_kg=77.5,
        source="healthkit",
        source_id="hk-latest",
        measured_at=now,
    )
    await db_session.commit()

    latest = await weight_sync_service.get_latest_weight(db_session, "test_latest")

    assert latest is not None
    assert latest["weight_kg"] == 77.5
    assert latest["source"] == "healthkit"
    assert latest["source_id"] == "hk-latest"
    assert latest["synced_at"] is not None
    assert latest["last_sync_time"] is not None
    assert latest["trend"] == "up"
    assert latest["delta_kg"] == 0.5


@pytest.mark.asyncio
async def test_weight_outside_dedupe_window_creates_new_entry(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Weight entry outside the dedupe time window should create a new entry.
    """
    user = UserProfile(user_id="test_window", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # First sync
    status1, entry1, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_window",
        weight_kg=70.0,
        source="google_fit",
        measured_at=now - datetime.timedelta(minutes=DEDUPE_WINDOW_MINUTES + 5),
    )
    await db_session.flush()
    entry1_id = entry1.id
    await db_session.commit()

    # Second sync outside window (same weight)
    status2, entry2, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_window",
        weight_kg=70.0,
        source="google_fit",
        measured_at=now,
    )
    await db_session.flush()
    entry2_id = entry2.id
    await db_session.commit()

    assert status1 == "created"
    assert status2 == "created"
    assert entry1_id != entry2_id


@pytest.mark.asyncio
async def test_weight_outside_tolerance_creates_new_entry(db_session: AsyncSession, weight_sync_service: WeightSyncService):
    """
    Weight entry outside the weight tolerance should create a new entry.
    """
    user = UserProfile(user_id="test_tolerance", target_calories=2000, target_protein_g=150)
    db_session.add(user)
    await db_session.commit()

    now = datetime.datetime.utcnow()

    # First sync
    status1, entry1, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_tolerance",
        weight_kg=70.0,
        source="google_fit",
        measured_at=now,
    )
    await db_session.flush()
    entry1_id = entry1.id
    await db_session.commit()

    # Second sync within time window but outside weight tolerance
    status2, entry2, _, _ = await weight_sync_service.sync_weight(
        db=db_session,
        user_id="test_tolerance",
        weight_kg=70.0 + DEDUPE_WEIGHT_TOLERANCE_KG + 0.1,  # Outside tolerance
        source="google_fit",
        measured_at=now + datetime.timedelta(minutes=1),
    )
    await db_session.flush()
    entry2_id = entry2.id
    await db_session.commit()

    assert status1 == "created"
    assert status2 == "created"
    assert entry1_id != entry2_id
