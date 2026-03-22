"""
AI Fitness Coach v1 — Import Service

Handles validation and restoration of audit bundles.
"""
import json
import os
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision, WorkoutLog, AdherenceRecord
from app.schemas.admin import (
    RestoreMode,
    ImportPreview,
    EntityPreview,
    CollectionPreview,
    ImportPreviewResponse,
    ImportResults,
    EntityResult,
    CollectionResult,
    ImportRestoreResponse,
)
from app.logging_config import get_logger

logger = get_logger("import_service")

# Bundle validation constants
REQUIRED_FIELDS = ["metadata", "user"]
SUPPORTED_VERSIONS = ["1.0"]
BACKUP_DIR = "backups"


class ImportService:
    """
    Service for importing and restoring audit bundles.

    Supports:
    - Schema validation
    - Conflict detection
    - Replace mode (with backup)
    - Merge mode (skip existing)
    - Dry-run for testing
    """

    def validate_bundle(self, bundle: dict) -> tuple[bool, list[str]]:
        """
        Validate bundle schema and version.

        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors = []

        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in bundle:
                errors.append(f"Missing required field: {field}")

        # Check metadata
        metadata = bundle.get("metadata", {})
        if not metadata:
            errors.append("Missing or empty metadata")
        else:
            version = metadata.get("version")
            if version not in SUPPORTED_VERSIONS:
                errors.append(f"Unsupported bundle version: {version}")

            if not metadata.get("user_id"):
                errors.append("Missing user_id in metadata")

        # Check user data
        user_data = bundle.get("user")
        if user_data and not user_data.get("id"):
            errors.append("User data missing id field")

        return len(errors) == 0, errors

    async def preview_restore(
        self,
        db: AsyncSession,
        bundle: dict,
        target_user_id: Optional[str] = None,
    ) -> ImportPreviewResponse:
        """
        Preview what will be restored without making changes.

        Detects conflicts and generates warnings.
        """
        # Validate bundle
        valid, errors = self.validate_bundle(bundle)
        if not valid:
            return ImportPreviewResponse(
                valid=False,
                errors=errors,
            )

        metadata = bundle.get("metadata", {})
        source_user_id = metadata.get("user_id")
        effective_user_id = target_user_id or source_user_id

        # Get existing data
        existing = await self._get_existing_data(db, effective_user_id)

        # Build preview
        preview = self._build_preview(bundle, existing)

        # Detect conflicts
        conflicts = self._detect_conflicts(bundle, existing)

        # Generate warnings
        warnings = self._generate_warnings(bundle, existing, target_user_id)

        return ImportPreviewResponse(
            valid=True,
            bundle_version=metadata.get("version"),
            source_user_id=source_user_id,
            target_user_id=effective_user_id,
            exported_at=metadata.get("exported_at"),
            preview=preview,
            conflicts=conflicts,
            warnings=warnings,
            dry_run_available=True,
        )

    async def execute_restore(
        self,
        db: AsyncSession,
        bundle: dict,
        mode: RestoreMode,
        dry_run: bool = False,
        target_user_id: Optional[str] = None,
    ) -> ImportRestoreResponse:
        """
        Execute the restore operation.

        Args:
            bundle: The audit bundle to restore
            mode: replace (delete existing) or merge (add new only)
            dry_run: If true, validate without committing
            target_user_id: Override user ID for restore
        """
        # Validate bundle
        valid, errors = self.validate_bundle(bundle)
        if not valid:
            return ImportRestoreResponse(
                success=False,
                mode=mode.value,
                dry_run=dry_run,
                target_user_id=target_user_id or "",
                errors=errors,
                message="Bundle validation failed",
            )

        metadata = bundle.get("metadata", {})
        source_user_id = metadata.get("user_id")
        effective_user_id = target_user_id or source_user_id

        backup_id = None
        results_errors = []

        try:
            # Create backup before replace mode
            if mode == RestoreMode.replace and not dry_run:
                backup_id = await self._create_backup(db, effective_user_id)

            # Get existing data for merge mode checks
            existing = await self._get_existing_data(db, effective_user_id)

            # Clear existing data in replace mode
            if mode == RestoreMode.replace and not dry_run:
                await self._clear_user_data(db, effective_user_id)

            # Restore each entity type
            user_result = await self._restore_user(
                db, bundle, effective_user_id, mode, existing, dry_run
            )
            profile_result = await self._restore_profile(
                db, bundle, effective_user_id, mode, existing, dry_run
            )

            # Track ID mappings for related records
            id_map = {"plans": {}, "revisions": {}}

            weight_result = await self._restore_weight_entries(
                db, bundle, effective_user_id, mode, existing, dry_run
            )
            plans_result, id_map["plans"] = await self._restore_plans(
                db, bundle, effective_user_id, mode, existing, dry_run
            )
            revisions_result, id_map["revisions"] = await self._restore_revisions(
                db, bundle, effective_user_id, mode, existing, id_map, dry_run
            )
            logs_result = await self._restore_workout_logs(
                db, bundle, effective_user_id, mode, existing, id_map, dry_run
            )
            adherence_result = await self._restore_adherence(
                db, bundle, effective_user_id, mode, existing, id_map, dry_run
            )

            results = ImportResults(
                user=user_result,
                profile=profile_result,
                weight_entries=weight_result,
                plans=plans_result,
                revisions=revisions_result,
                workout_logs=logs_result,
                adherence_records=adherence_result,
            )

            # Commit or rollback
            if dry_run:
                await db.rollback()
                message = f"Dry run complete - would restore to user {effective_user_id}"
            else:
                await db.commit()
                total = self._count_results(results)
                message = f"Restored {total} records for user {effective_user_id}"

            logger.info(
                "restore_complete",
                user_id=effective_user_id,
                mode=mode.value,
                dry_run=dry_run,
                backup_id=backup_id,
            )

            return ImportRestoreResponse(
                success=True,
                mode=mode.value,
                dry_run=dry_run,
                target_user_id=effective_user_id,
                backup_id=backup_id,
                results=results,
                message=message,
            )

        except Exception as e:
            await db.rollback()
            logger.error("restore_failed", error=str(e), user_id=effective_user_id)
            return ImportRestoreResponse(
                success=False,
                mode=mode.value,
                dry_run=dry_run,
                target_user_id=effective_user_id,
                backup_id=backup_id,
                errors=[str(e)],
                message="Restore failed - see errors",
            )

    async def _get_existing_data(self, db: AsyncSession, user_id: str) -> dict:
        """Get summary of existing data for conflict detection."""
        existing = {
            "user_exists": False,
            "profile_exists": False,
            "weight_keys": set(),
            "plan_ids": set(),
            "revision_ids": set(),
            "log_ids": set(),
            "adherence_ids": set(),
        }

        # User
        result = await db.execute(select(User).where(User.id == user_id))
        existing["user_exists"] = result.scalar_one_or_none() is not None

        # Profile
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        existing["profile_exists"] = result.scalar_one_or_none() is not None

        # Weight entries - key by (date, source)
        result = await db.execute(
            select(WeightEntry).where(WeightEntry.user_id == user_id)
        )
        for entry in result.scalars().all():
            date_str = entry.date.isoformat() if hasattr(entry.date, 'isoformat') else str(entry.date)
            existing["weight_keys"].add((date_str, entry.source))

        # Plans
        result = await db.execute(
            select(WeeklyPlan).where(WeeklyPlan.user_id == user_id)
        )
        existing["plan_ids"] = {p.id for p in result.scalars().all()}

        # Revisions
        result = await db.execute(
            select(PlanRevision).where(PlanRevision.user_id == user_id)
        )
        existing["revision_ids"] = {r.id for r in result.scalars().all()}

        # Workout logs
        result = await db.execute(
            select(WorkoutLog).where(WorkoutLog.user_id == user_id)
        )
        existing["log_ids"] = {log.id for log in result.scalars().all()}

        # Adherence
        result = await db.execute(
            select(AdherenceRecord).where(AdherenceRecord.user_id == user_id)
        )
        existing["adherence_ids"] = {a.id for a in result.scalars().all()}

        return existing

    def _build_preview(self, bundle: dict, existing: dict) -> ImportPreview:
        """Build preview of what will be restored."""
        # User
        user_data = bundle.get("user")
        user_preview = EntityPreview(
            action="update" if existing["user_exists"] else "create",
            exists=existing["user_exists"],
        )

        # Profile
        profile_data = bundle.get("profile")
        profile_preview = EntityPreview(
            action="update" if existing["profile_exists"] else "create",
            exists=existing["profile_exists"],
        )

        # Weight entries
        weight_entries = bundle.get("weight_entries", [])
        weight_new = 0
        weight_existing = 0
        for entry in weight_entries:
            date_str = entry.get("date", "")
            key = (date_str, entry.get("source"))
            if key in existing["weight_keys"]:
                weight_existing += 1
            else:
                weight_new += 1

        # Plans
        plans = bundle.get("plans", [])
        plans_new = sum(1 for p in plans if p.get("id") not in existing["plan_ids"])
        plans_existing = len(plans) - plans_new

        # Revisions
        revisions = bundle.get("revisions", [])
        rev_new = sum(1 for r in revisions if r.get("id") not in existing["revision_ids"])
        rev_existing = len(revisions) - rev_new

        # Workout logs
        logs = bundle.get("workout_logs", [])
        logs_new = sum(1 for l in logs if l.get("id") not in existing["log_ids"])
        logs_existing = len(logs) - logs_new

        # Adherence
        adherence = bundle.get("adherence_records", [])
        adh_new = sum(1 for a in adherence if a.get("id") not in existing["adherence_ids"])
        adh_existing = len(adherence) - adh_new

        return ImportPreview(
            user=user_preview,
            profile=profile_preview,
            weight_entries=CollectionPreview(
                count=len(weight_entries), new=weight_new, existing=weight_existing
            ),
            plans=CollectionPreview(
                count=len(plans), new=plans_new, existing=plans_existing
            ),
            revisions=CollectionPreview(
                count=len(revisions), new=rev_new, existing=rev_existing
            ),
            workout_logs=CollectionPreview(
                count=len(logs), new=logs_new, existing=logs_existing
            ),
            adherence_records=CollectionPreview(
                count=len(adherence), new=adh_new, existing=adh_existing
            ),
        )

    def _detect_conflicts(self, bundle: dict, existing: dict) -> list[str]:
        """Detect potential conflicts in merge mode."""
        conflicts = []

        # Plan ID conflicts
        for plan in bundle.get("plans", []):
            if plan.get("id") in existing["plan_ids"]:
                conflicts.append(f"Plan '{plan.get('id')}' already exists")

        # Revision ID conflicts
        for rev in bundle.get("revisions", []):
            if rev.get("id") in existing["revision_ids"]:
                conflicts.append(f"Revision '{rev.get('id')}' already exists")

        return conflicts

    def _generate_warnings(
        self,
        bundle: dict,
        existing: dict,
        target_user_id: Optional[str],
    ) -> list[str]:
        """Generate warnings about the import."""
        warnings = []

        if existing["user_exists"]:
            warnings.append("User already exists - will be updated in replace mode")

        if existing["profile_exists"]:
            warnings.append("Profile already exists - will be updated in replace mode")

        if target_user_id:
            source_id = bundle.get("metadata", {}).get("user_id")
            if source_id and source_id != target_user_id:
                warnings.append(
                    f"Restoring to different user: {source_id} -> {target_user_id}"
                )

        # Check for large amounts of data
        weight_count = len(bundle.get("weight_entries", []))
        if weight_count > 100:
            warnings.append(f"Large weight history: {weight_count} entries")

        return warnings

    async def _create_backup(self, db: AsyncSession, user_id: str) -> Optional[str]:
        """Create a backup of existing user data before replace."""
        # Ensure backup directory exists
        os.makedirs(BACKUP_DIR, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        backup_id = f"backup-{timestamp}-{user_id}"
        backup_path = os.path.join(BACKUP_DIR, f"{backup_id}.json")

        # Build backup bundle (simplified version of export)
        bundle: dict[str, Any] = {"metadata": {}, "user": None, "profile": None}

        # User
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            bundle["user"] = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }

        # Profile
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            bundle["profile"] = {
                "user_id": profile.user_id,
                "goal": profile.goal,
                "equipment": profile.equipment,
                "days_per_week": profile.days_per_week,
                "session_length_min": profile.session_length_min,
                "target_calories": profile.target_calories,
                "target_protein_g": profile.target_protein_g,
                "target_carbs_g": profile.target_carbs_g,
                "target_fat_g": profile.target_fat_g,
                "height_cm": profile.height_cm,
                "weight_kg": profile.weight_kg,
                "age": profile.age,
                "sex": profile.sex,
            }

        # Weight entries
        result = await db.execute(
            select(WeightEntry).where(WeightEntry.user_id == user_id)
        )
        bundle["weight_entries"] = [
            {
                "id": w.id,
                "weight_kg": w.weight_kg,
                "date": w.date.isoformat() if hasattr(w.date, 'isoformat') else str(w.date),
                "source": w.source,
            }
            for w in result.scalars().all()
        ]

        # Plans
        result = await db.execute(
            select(WeeklyPlan).where(WeeklyPlan.user_id == user_id)
        )
        bundle["plans"] = [{"id": p.id, "status": p.status} for p in result.scalars().all()]

        # Revisions
        result = await db.execute(
            select(PlanRevision).where(PlanRevision.user_id == user_id)
        )
        bundle["revisions"] = [
            {"id": r.id, "status": r.status} for r in result.scalars().all()
        ]

        bundle["metadata"] = {
            "user_id": user_id,
            "backed_up_at": datetime.utcnow().isoformat(),
            "backup_id": backup_id,
        }

        # Write backup file
        with open(backup_path, "w") as f:
            json.dump(bundle, f, indent=2, default=str)

        logger.info("backup_created", backup_id=backup_id, path=backup_path)
        return backup_id

    async def _clear_user_data(self, db: AsyncSession, user_id: str):
        """Delete all data for a user (reuse seed_data logic)."""
        await db.execute(delete(PlanRevision).where(PlanRevision.user_id == user_id))
        await db.execute(delete(WorkoutLog).where(WorkoutLog.user_id == user_id))
        await db.execute(delete(AdherenceRecord).where(AdherenceRecord.user_id == user_id))
        await db.execute(delete(WeeklyPlan).where(WeeklyPlan.user_id == user_id))
        await db.execute(delete(WeightEntry).where(WeightEntry.user_id == user_id))
        await db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.flush()
        logger.info("cleared_user_data", user_id=user_id)

    async def _restore_user(
        self,
        db: AsyncSession,
        bundle: dict,
        user_id: str,
        mode: RestoreMode,
        existing: dict,
        dry_run: bool,
    ) -> EntityResult:
        """Restore user record."""
        user_data = bundle.get("user")
        if not user_data:
            return EntityResult(action="skipped", success=True)

        if mode == RestoreMode.merge and existing["user_exists"]:
            return EntityResult(action="skipped", success=True)

        if dry_run:
            action = "updated" if existing["user_exists"] else "created"
            return EntityResult(action=action, success=True)

        # Create or update user
        user = User(
            id=user_id,
            username=user_data.get("username", f"user_{user_id[:8]}"),
            email=user_data.get("email"),
            is_active=user_data.get("is_active", True),
        )

        # Preserve original created_at if available
        if user_data.get("created_at"):
            user.created_at = self._parse_datetime(user_data["created_at"])

        db.add(user)
        await db.flush()

        return EntityResult(
            action="updated" if existing["user_exists"] else "created",
            success=True,
        )

    async def _restore_profile(
        self,
        db: AsyncSession,
        bundle: dict,
        user_id: str,
        mode: RestoreMode,
        existing: dict,
        dry_run: bool,
    ) -> EntityResult:
        """Restore user profile."""
        profile_data = bundle.get("profile")
        if not profile_data:
            return EntityResult(action="skipped", success=True)

        if mode == RestoreMode.merge and existing["profile_exists"]:
            return EntityResult(action="skipped", success=True)

        if dry_run:
            action = "updated" if existing["profile_exists"] else "created"
            return EntityResult(action=action, success=True)

        profile = UserProfile(
            user_id=user_id,
            goal=profile_data.get("goal"),
            equipment=profile_data.get("equipment", []),
            days_per_week=profile_data.get("days_per_week"),
            session_length_min=profile_data.get("session_length_min"),
            preferred_workout_time=profile_data.get("preferred_workout_time"),
            target_calories=profile_data.get("target_calories"),
            target_protein_g=profile_data.get("target_protein_g"),
            target_carbs_g=profile_data.get("target_carbs_g"),
            target_fat_g=profile_data.get("target_fat_g"),
            dietary_restrictions=profile_data.get("dietary_restrictions", []),
            dietary_preferences=profile_data.get("dietary_preferences", []),
            injuries=profile_data.get("injuries", []),
            health_conditions=profile_data.get("health_conditions", []),
            height_cm=profile_data.get("height_cm"),
            weight_kg=profile_data.get("weight_kg"),
            age=profile_data.get("age"),
            sex=profile_data.get("sex"),
            body_fat_pct=profile_data.get("body_fat_pct"),
            activity_level=profile_data.get("activity_level"),
            coaching_persona=profile_data.get("coaching_persona"),
            replan_weight_threshold_kg=profile_data.get("replan_weight_threshold_kg"),
            replan_missed_workout_threshold=profile_data.get("replan_missed_workout_threshold"),
            replan_cooldown_days=profile_data.get("replan_cooldown_days"),
        )

        if profile_data.get("created_at"):
            profile.created_at = self._parse_datetime(profile_data["created_at"])

        db.add(profile)
        await db.flush()

        return EntityResult(
            action="updated" if existing["profile_exists"] else "created",
            success=True,
        )

    async def _restore_weight_entries(
        self,
        db: AsyncSession,
        bundle: dict,
        user_id: str,
        mode: RestoreMode,
        existing: dict,
        dry_run: bool,
    ) -> CollectionResult:
        """Restore weight entries."""
        entries = bundle.get("weight_entries", [])
        result = CollectionResult()

        for entry_data in entries:
            date_str = entry_data.get("date", "")
            key = (date_str, entry_data.get("source"))

            # Skip existing in merge mode
            if mode == RestoreMode.merge and key in existing["weight_keys"]:
                result.skipped += 1
                continue

            if dry_run:
                result.created += 1
                continue

            entry = WeightEntry(
                id=str(uuid4()),  # New ID
                user_id=user_id,
                weight_kg=entry_data.get("weight_kg"),
                date=self._parse_datetime(date_str),
                source=entry_data.get("source", "manual"),
                source_id=entry_data.get("source_id"),
                synced_at=self._parse_datetime(entry_data.get("synced_at")),
                notes=entry_data.get("notes"),
            )

            if entry_data.get("created_at"):
                entry.created_at = self._parse_datetime(entry_data["created_at"])

            db.add(entry)
            result.created += 1

        if not dry_run:
            await db.flush()

        return result

    async def _restore_plans(
        self,
        db: AsyncSession,
        bundle: dict,
        user_id: str,
        mode: RestoreMode,
        existing: dict,
        dry_run: bool,
    ) -> tuple[CollectionResult, dict[str, str]]:
        """Restore weekly plans and return ID mapping."""
        plans = bundle.get("plans", [])
        result = CollectionResult()
        id_map: dict[str, str] = {}

        for plan_data in plans:
            old_id = plan_data.get("id")

            # Skip existing in merge mode
            if mode == RestoreMode.merge and old_id in existing["plan_ids"]:
                result.skipped += 1
                id_map[old_id] = old_id  # Keep same ID
                continue

            # Generate new ID
            new_id = f"plan-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid4())[:8]}"
            id_map[old_id] = new_id

            if dry_run:
                result.created += 1
                continue

            plan = WeeklyPlan(
                id=new_id,
                user_id=user_id,
                week_start=self._parse_datetime(plan_data.get("week_start")),
                week_end=self._parse_datetime(plan_data.get("week_end")),
                status=plan_data.get("status", "active"),
                workout_plan=plan_data.get("workout_plan", {}),
                meal_plan=plan_data.get("meal_plan", {}),
                shopping_list=plan_data.get("shopping_list", []),
                llm_reasoning=plan_data.get("llm_reasoning"),
                rules_applied=plan_data.get("rules_applied", []),
            )

            if plan_data.get("created_at"):
                plan.created_at = self._parse_datetime(plan_data["created_at"])

            db.add(plan)
            result.created += 1

        if not dry_run:
            await db.flush()

        return result, id_map

    async def _restore_revisions(
        self,
        db: AsyncSession,
        bundle: dict,
        user_id: str,
        mode: RestoreMode,
        existing: dict,
        id_map: dict,
        dry_run: bool,
    ) -> tuple[CollectionResult, dict[str, str]]:
        """Restore plan revisions with ID mapping."""
        revisions = bundle.get("revisions", [])
        result = CollectionResult()
        rev_id_map: dict[str, str] = {}

        for rev_data in revisions:
            old_id = rev_data.get("id")

            # Skip existing in merge mode
            if mode == RestoreMode.merge and old_id in existing["revision_ids"]:
                result.skipped += 1
                rev_id_map[old_id] = old_id
                continue

            new_id = str(uuid4())
            rev_id_map[old_id] = new_id

            if dry_run:
                result.created += 1
                continue

            # Map plan ID
            old_plan_id = rev_data.get("plan_id")
            new_plan_id = id_map.get("plans", {}).get(old_plan_id, old_plan_id)

            # Map parent and superseded revision IDs
            old_parent_id = rev_data.get("parent_revision_id")
            new_parent_id = rev_id_map.get(old_parent_id) if old_parent_id else None

            old_superseded_id = rev_data.get("superseded_by_id")
            new_superseded_id = rev_id_map.get(old_superseded_id) if old_superseded_id else None

            revision = PlanRevision(
                id=new_id,
                plan_id=new_plan_id,
                user_id=user_id,
                revision_number=rev_data.get("revision_number", 1),
                trigger=rev_data.get("trigger"),
                target_area=rev_data.get("target_area"),
                reason=rev_data.get("reason"),
                patch=rev_data.get("patch", {}),
                status=rev_data.get("status", "pending"),
                status_reason=rev_data.get("status_reason"),
                is_auto_applied=rev_data.get("is_auto_applied", False),
                parent_revision_id=new_parent_id,
                superseded_by_id=new_superseded_id,
            )

            if rev_data.get("created_at"):
                revision.created_at = self._parse_datetime(rev_data["created_at"])

            db.add(revision)
            result.created += 1

        if not dry_run:
            await db.flush()

        return result, rev_id_map

    async def _restore_workout_logs(
        self,
        db: AsyncSession,
        bundle: dict,
        user_id: str,
        mode: RestoreMode,
        existing: dict,
        id_map: dict,
        dry_run: bool,
    ) -> CollectionResult:
        """Restore workout logs."""
        logs = bundle.get("workout_logs", [])
        result = CollectionResult()

        for log_data in logs:
            old_id = log_data.get("id")

            # Skip existing in merge mode
            if mode == RestoreMode.merge and old_id in existing["log_ids"]:
                result.skipped += 1
                continue

            if dry_run:
                result.created += 1
                continue

            # Map plan ID
            old_plan_id = log_data.get("plan_id")
            new_plan_id = id_map.get("plans", {}).get(old_plan_id, old_plan_id)

            # Handle synced_to_wger - model uses String(20), not Boolean
            synced_to_wger = log_data.get("synced_to_wger", "pending")
            if isinstance(synced_to_wger, bool):
                synced_to_wger = "synced" if synced_to_wger else "pending"

            log = WorkoutLog(
                id=str(uuid4()),
                user_id=user_id,
                plan_id=new_plan_id,
                date=self._parse_datetime(log_data.get("date")),
                exercises_completed=log_data.get("exercises_completed", []),
                completion_pct=log_data.get("completion_pct", 0.0),
                duration_min=log_data.get("duration_min"),
                energy_level=log_data.get("energy_level"),
                notes=log_data.get("notes"),
                synced_to_wger=synced_to_wger,
            )

            if log_data.get("created_at"):
                log.created_at = self._parse_datetime(log_data["created_at"])

            db.add(log)
            result.created += 1

        if not dry_run:
            await db.flush()

        return result

    async def _restore_adherence(
        self,
        db: AsyncSession,
        bundle: dict,
        user_id: str,
        mode: RestoreMode,
        existing: dict,
        id_map: dict,
        dry_run: bool,
    ) -> CollectionResult:
        """Restore adherence records."""
        records = bundle.get("adherence_records", [])
        result = CollectionResult()

        for record_data in records:
            old_id = record_data.get("id")

            # Skip existing in merge mode
            if mode == RestoreMode.merge and old_id in existing["adherence_ids"]:
                result.skipped += 1
                continue

            if dry_run:
                result.created += 1
                continue

            # Handle workout_completed - model uses String(10), not Boolean
            workout_completed = record_data.get("workout_completed", False)
            if isinstance(workout_completed, bool):
                workout_completed = "true" if workout_completed else "false"

            record = AdherenceRecord(
                id=str(uuid4()),
                user_id=user_id,
                date=self._parse_datetime(record_data.get("date")),
                workout_planned=record_data.get("workout_planned", "false"),
                workout_completed=workout_completed,
                workout_completion_pct=record_data.get("workout_completion_pct", 0.0),
                meals_planned=record_data.get("meals_planned", 0),
                meals_followed=record_data.get("meals_followed", record_data.get("meals_logged", 0)),
                calories_actual=record_data.get("calories_actual"),
                protein_actual_g=record_data.get("protein_actual_g"),
                energy_level=record_data.get("energy_level"),
                hunger_level=record_data.get("hunger_level"),
                sleep_quality=record_data.get("sleep_quality"),
                mood=record_data.get("mood"),
            )

            if record_data.get("created_at"):
                record.created_at = self._parse_datetime(record_data["created_at"])

            db.add(record)
            result.created += 1

        if not dry_run:
            await db.flush()

        return result

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from string or return None."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Handle ISO format with or without timezone
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _count_results(self, results: ImportResults) -> int:
        """Count total records restored."""
        total = 0
        if results.user.action in ("created", "updated"):
            total += 1
        if results.profile.action in ("created", "updated"):
            total += 1
        total += results.weight_entries.created
        total += results.plans.created
        total += results.revisions.created
        total += results.workout_logs.created
        total += results.adherence_records.created
        return total
