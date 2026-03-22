"""
Tests for audit bundle import/restore functionality.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func

from app.database import Base
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision, WorkoutLog, AdherenceRecord
from app.services.seed_data import SeedDataService, DEMO_USER_ID
from app.services.import_service import ImportService
from app.schemas.admin import RestoreMode


SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


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
async def import_service():
    return ImportService()


@pytest_asyncio.fixture
async def seed_service():
    return SeedDataService()


def create_minimal_bundle(user_id: str = "test-user-001") -> dict:
    """Create a minimal valid bundle for testing."""
    return {
        "metadata": {
            "user_id": user_id,
            "exported_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "record_counts": {"user": 1, "profile": 1},
        },
        "user": {
            "id": user_id,
            "username": "testuser",
            "email": "test@example.com",
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
        },
        "profile": {
            "user_id": user_id,
            "goal": "fat_loss",
            "equipment": ["barbell", "dumbbells"],
            "days_per_week": 4,
            "session_length_min": 60,
            "target_calories": 2200,
            "target_protein_g": 180,
            "height_cm": 178.0,
            "weight_kg": 85.0,
            "age": 32,
            "sex": "male",
        },
        "weight_entries": [],
        "plans": [],
        "revisions": [],
        "workout_logs": [],
        "adherence_records": [],
    }


def create_full_bundle(user_id: str = "test-user-001") -> dict:
    """Create a full bundle with all entity types."""
    now = datetime.utcnow()
    bundle = create_minimal_bundle(user_id)

    # Add weight entries
    bundle["weight_entries"] = [
        {
            "id": "weight-1",
            "user_id": user_id,
            "weight_kg": 85.0,
            "date": (now - timedelta(days=7)).isoformat(),
            "source": "manual",
            "created_at": (now - timedelta(days=7)).isoformat(),
        },
        {
            "id": "weight-2",
            "user_id": user_id,
            "weight_kg": 84.5,
            "date": now.isoformat(),
            "source": "healthkit",
            "source_id": "HK-12345",
            "created_at": now.isoformat(),
        },
    ]

    # Add a plan
    plan_id = f"plan-{user_id}-20240115"
    bundle["plans"] = [
        {
            "id": plan_id,
            "user_id": user_id,
            "week_start": (now - timedelta(days=now.weekday())).isoformat(),
            "week_end": (now - timedelta(days=now.weekday()) + timedelta(days=6)).isoformat(),
            "status": "active",
            "workout_plan": {"days": []},
            "meal_plan": {"days": []},
            "shopping_list": [],
            "created_at": (now - timedelta(days=3)).isoformat(),
        }
    ]

    # Add revisions
    bundle["revisions"] = [
        {
            "id": "rev-1",
            "plan_id": plan_id,
            "user_id": user_id,
            "revision_number": 1,
            "trigger": "weight_change",
            "target_area": "nutrition",
            "reason": "Weight increased, reducing calories",
            "patch": {"calorie_adjust": -150},
            "status": "applied",
            "is_auto_applied": True,
            "created_at": (now - timedelta(days=2)).isoformat(),
        }
    ]

    # Add workout log
    bundle["workout_logs"] = [
        {
            "id": "log-1",
            "user_id": user_id,
            "plan_id": plan_id,
            "date": (now - timedelta(days=1)).isoformat(),
            "exercises_completed": [{"name": "Bench Press", "sets": 4}],
            "completion_pct": 100.0,
            "duration_min": 55,
            "energy_level": 4,
            "created_at": (now - timedelta(days=1)).isoformat(),
        }
    ]

    # Add adherence record
    bundle["adherence_records"] = [
        {
            "id": "adh-1",
            "user_id": user_id,
            "date": (now - timedelta(days=1)).isoformat(),
            "workout_planned": "true",
            "workout_completed": "true",
            "meals_planned": 3,
            "meals_followed": 3,
            "created_at": (now - timedelta(days=1)).isoformat(),
        }
    ]

    return bundle


# --- Bundle Validation Tests ---


@pytest.mark.asyncio
async def test_validate_bundle_valid(import_service: ImportService):
    """Verify valid bundle passes validation."""
    bundle = create_minimal_bundle()
    valid, errors = import_service.validate_bundle(bundle)

    assert valid is True
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_validate_bundle_missing_metadata(import_service: ImportService):
    """Verify bundle without metadata fails validation."""
    bundle = {"user": {"id": "test"}}
    valid, errors = import_service.validate_bundle(bundle)

    assert valid is False
    assert any("metadata" in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_validate_bundle_missing_user(import_service: ImportService):
    """Verify bundle without user field fails validation."""
    bundle = {"metadata": {"user_id": "test", "version": "1.0"}}
    valid, errors = import_service.validate_bundle(bundle)

    assert valid is False
    assert any("user" in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_validate_bundle_unsupported_version(import_service: ImportService):
    """Verify bundle with unsupported version fails validation."""
    bundle = create_minimal_bundle()
    bundle["metadata"]["version"] = "99.0"
    valid, errors = import_service.validate_bundle(bundle)

    assert valid is False
    assert any("version" in e.lower() for e in errors)


# --- Preview Tests ---


@pytest.mark.asyncio
async def test_preview_valid_bundle(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify preview returns correct structure for valid bundle."""
    bundle = create_full_bundle()
    response = await import_service.preview_restore(db_session, bundle)

    assert response.valid is True
    assert response.bundle_version == "1.0"
    assert response.source_user_id == "test-user-001"
    assert response.target_user_id == "test-user-001"
    assert response.preview is not None
    assert response.preview.user.action == "create"
    assert response.preview.user.exists is False
    assert response.preview.weight_entries.count == 2
    assert response.preview.plans.count == 1


@pytest.mark.asyncio
async def test_preview_invalid_bundle(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify preview returns errors for invalid bundle."""
    bundle = {"incomplete": True}
    response = await import_service.preview_restore(db_session, bundle)

    assert response.valid is False
    assert len(response.errors) > 0


@pytest.mark.asyncio
async def test_preview_detects_existing_user(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify preview detects when user already exists."""
    # Create existing user
    user = User(id="existing-user", username="existing", email="exist@test.com")
    db_session.add(user)
    await db_session.commit()

    bundle = create_minimal_bundle("existing-user")
    response = await import_service.preview_restore(db_session, bundle)

    assert response.valid is True
    assert response.preview.user.exists is True
    assert response.preview.user.action == "update"
    assert any("already exists" in w for w in response.warnings)


@pytest.mark.asyncio
async def test_preview_detects_conflicts(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify preview detects plan ID conflicts."""
    # Create existing plan
    user = User(id="conflict-user", username="conflict", email="c@test.com")
    db_session.add(user)
    await db_session.flush()

    plan = WeeklyPlan(
        id="existing-plan-id",
        user_id="conflict-user",
        week_start=datetime.utcnow(),
        week_end=datetime.utcnow(),
        status="active",
    )
    db_session.add(plan)
    await db_session.commit()

    # Bundle with same plan ID
    bundle = create_minimal_bundle("conflict-user")
    bundle["plans"] = [{"id": "existing-plan-id", "user_id": "conflict-user", "status": "active"}]

    response = await import_service.preview_restore(db_session, bundle)

    assert response.valid is True
    assert len(response.conflicts) > 0
    assert any("existing-plan-id" in c for c in response.conflicts)


@pytest.mark.asyncio
async def test_preview_with_target_user_override(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify preview handles target user ID override."""
    bundle = create_minimal_bundle("source-user")
    response = await import_service.preview_restore(
        db_session, bundle, target_user_id="different-user"
    )

    assert response.valid is True
    assert response.source_user_id == "source-user"
    assert response.target_user_id == "different-user"
    assert any("different user" in w.lower() for w in response.warnings)


# --- Restore Tests ---


@pytest.mark.asyncio
async def test_restore_to_empty_user(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify restore creates all entities for new user."""
    bundle = create_full_bundle("new-user")
    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.replace, dry_run=False
    )

    assert response.success is True
    assert response.mode == "replace"
    assert response.target_user_id == "new-user"
    assert response.results.user.action == "created"
    assert response.results.profile.action == "created"
    assert response.results.weight_entries.created == 2
    assert response.results.plans.created == 1
    assert response.results.revisions.created == 1

    # Verify data in database
    result = await db_session.execute(select(User).where(User.id == "new-user"))
    user = result.scalar_one()
    assert user.username == "testuser"

    result = await db_session.execute(select(UserProfile).where(UserProfile.user_id == "new-user"))
    profile = result.scalar_one()
    assert profile.goal == "fat_loss"


@pytest.mark.asyncio
async def test_restore_replace_mode_clears_existing(
    db_session: AsyncSession,
    import_service: ImportService,
    seed_service: SeedDataService,
):
    """Verify replace mode deletes existing data first."""
    # Seed demo data
    await seed_service.seed_demo_user(db_session, "replace-user")

    # Count existing
    result = await db_session.execute(
        select(func.count()).select_from(WeightEntry).where(
            WeightEntry.user_id == "replace-user"
        )
    )
    initial_count = result.scalar()
    assert initial_count == 15

    # Replace with bundle containing only 2 entries
    bundle = create_full_bundle("replace-user")
    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.replace, dry_run=False
    )

    assert response.success is True
    assert response.backup_id is not None  # Backup created

    # Verify old data cleared, new data present
    result = await db_session.execute(
        select(func.count()).select_from(WeightEntry).where(
            WeightEntry.user_id == "replace-user"
        )
    )
    new_count = result.scalar()
    assert new_count == 2  # Only from bundle


@pytest.mark.asyncio
async def test_restore_merge_mode_skips_existing(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify merge mode skips existing records."""
    # Create existing user
    user = User(id="merge-user", username="existing", email="m@test.com")
    db_session.add(user)
    await db_session.commit()

    # Try to merge bundle
    bundle = create_minimal_bundle("merge-user")
    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.merge, dry_run=False
    )

    assert response.success is True
    assert response.results.user.action == "skipped"  # Existing user skipped


@pytest.mark.asyncio
async def test_restore_dry_run_does_not_commit(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify dry run mode doesn't persist changes."""
    bundle = create_full_bundle("dryrun-user")
    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.replace, dry_run=True
    )

    assert response.success is True
    assert response.dry_run is True
    assert "dry run" in response.message.lower()

    # Verify no data persisted
    result = await db_session.execute(select(User).where(User.id == "dryrun-user"))
    user = result.scalar_one_or_none()
    assert user is None


@pytest.mark.asyncio
async def test_restore_creates_backup_before_replace(
    db_session: AsyncSession,
    import_service: ImportService,
    seed_service: SeedDataService,
):
    """Verify backup is created before replace mode."""
    # Seed data to backup
    await seed_service.seed_demo_user(db_session, "backup-user")

    bundle = create_minimal_bundle("backup-user")
    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.replace, dry_run=False
    )

    assert response.success is True
    assert response.backup_id is not None
    assert response.backup_id.startswith("backup-")


@pytest.mark.asyncio
async def test_restore_preserves_timestamps(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify restore preserves original created_at timestamps."""
    original_time = datetime(2024, 1, 15, 10, 30, 0)
    bundle = create_minimal_bundle("timestamp-user")
    bundle["user"]["created_at"] = original_time.isoformat()

    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.replace, dry_run=False
    )

    assert response.success is True

    result = await db_session.execute(select(User).where(User.id == "timestamp-user"))
    user = result.scalar_one()
    # Compare dates (SQLite may not preserve full precision)
    assert user.created_at.date() == original_time.date()


@pytest.mark.asyncio
async def test_restore_maps_plan_ids_for_related_records(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify workout logs and revisions get updated plan IDs."""
    bundle = create_full_bundle("mapping-user")
    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.replace, dry_run=False
    )

    assert response.success is True

    # Get the new plan
    result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.user_id == "mapping-user")
    )
    plan = result.scalar_one()

    # Verify workout log has the new plan ID
    result = await db_session.execute(
        select(WorkoutLog).where(WorkoutLog.user_id == "mapping-user")
    )
    log = result.scalar_one()
    assert log.plan_id == plan.id

    # Verify revision has the new plan ID
    result = await db_session.execute(
        select(PlanRevision).where(PlanRevision.user_id == "mapping-user")
    )
    revision = result.scalar_one()
    assert revision.plan_id == plan.id


# --- Roundtrip Tests ---


@pytest.mark.asyncio
async def test_roundtrip_export_import(
    db_session: AsyncSession,
    import_service: ImportService,
    seed_service: SeedDataService,
):
    """Verify data survives export → clear → import cycle."""
    from app.api.admin import _serialize_datetime
    from sqlalchemy import select

    # 1. Seed demo data
    await seed_service.seed_demo_user(db_session, "roundtrip-user")

    # 2. Export (simplified - just build bundle from DB)
    user_result = await db_session.execute(
        select(User).where(User.id == "roundtrip-user")
    )
    user = user_result.scalar_one()

    profile_result = await db_session.execute(
        select(UserProfile).where(UserProfile.user_id == "roundtrip-user")
    )
    profile = profile_result.scalar_one()

    weight_result = await db_session.execute(
        select(WeightEntry).where(WeightEntry.user_id == "roundtrip-user")
    )
    weights = weight_result.scalars().all()
    original_weight_count = len(weights)

    plan_result = await db_session.execute(
        select(WeeklyPlan).where(WeeklyPlan.user_id == "roundtrip-user")
    )
    plan = plan_result.scalar_one()

    # Build export bundle
    bundle = {
        "metadata": {
            "user_id": "roundtrip-user",
            "exported_at": datetime.utcnow().isoformat(),
            "version": "1.0",
        },
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "profile": {
            "user_id": profile.user_id,
            "goal": profile.goal,
            "equipment": profile.equipment,
            "days_per_week": profile.days_per_week,
            "target_calories": profile.target_calories,
        },
        "weight_entries": [
            {
                "id": w.id,
                "weight_kg": w.weight_kg,
                "date": w.date.isoformat() if hasattr(w.date, 'isoformat') else str(w.date),
                "source": w.source,
            }
            for w in weights
        ],
        "plans": [
            {
                "id": plan.id,
                "week_start": plan.week_start.isoformat() if plan.week_start else None,
                "week_end": plan.week_end.isoformat() if plan.week_end else None,
                "status": plan.status,
                "workout_plan": plan.workout_plan,
                "meal_plan": plan.meal_plan,
            }
        ],
        "revisions": [],
        "workout_logs": [],
        "adherence_records": [],
    }

    # 3. Clear data
    await seed_service._clear_user_data(db_session, "roundtrip-user")
    await db_session.commit()

    # Verify cleared
    result = await db_session.execute(select(User).where(User.id == "roundtrip-user"))
    assert result.scalar_one_or_none() is None

    # 4. Import
    response = await import_service.execute_restore(
        db_session, bundle, RestoreMode.replace, dry_run=False
    )

    assert response.success is True

    # 5. Verify data restored
    result = await db_session.execute(select(User).where(User.id == "roundtrip-user"))
    restored_user = result.scalar_one()
    assert restored_user.username == user.username

    result = await db_session.execute(
        select(UserProfile).where(UserProfile.user_id == "roundtrip-user")
    )
    restored_profile = result.scalar_one()
    assert restored_profile.goal == profile.goal

    result = await db_session.execute(
        select(func.count()).select_from(WeightEntry).where(
            WeightEntry.user_id == "roundtrip-user"
        )
    )
    restored_weight_count = result.scalar()
    assert restored_weight_count == original_weight_count


@pytest.mark.asyncio
async def test_restore_to_different_user(
    db_session: AsyncSession, import_service: ImportService
):
    """Verify bundle can be restored to a different user ID."""
    bundle = create_full_bundle("source-user")
    response = await import_service.execute_restore(
        db_session,
        bundle,
        RestoreMode.replace,
        dry_run=False,
        target_user_id="target-user",
    )

    assert response.success is True
    assert response.target_user_id == "target-user"

    # Verify data exists for target user
    result = await db_session.execute(select(User).where(User.id == "target-user"))
    user = result.scalar_one()
    assert user is not None

    # Verify source user does NOT exist
    result = await db_session.execute(select(User).where(User.id == "source-user"))
    assert result.scalar_one_or_none() is None
