"""
AI Fitness Coach v1 — Weight Sync Service

Handles external weight sync with deduplication and replan evaluation.
Keeps the architecture provider-based for future biometric sources.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_

from app.models.user import WeightEntry, UserProfile
from app.models.plan import WeeklyPlan, PlanRevision
from app.logging_config import get_logger

logger = get_logger("weight_sync")

# Dedupe configuration
DEDUPE_WINDOW_MINUTES = 5  # Entries within 5 minutes are considered duplicates
DEDUPE_WEIGHT_TOLERANCE_KG = 0.1  # Weight difference tolerance for dedupe


class WeightSyncService:
    """
    Service for syncing weight entries from external sources.

    Responsibilities:
    - Dedupe near-identical entries from the same source
    - Route synced weights through normal trend evaluation
    - Trigger replan only through the standard replanning path
    """

    async def sync_weight(
        self,
        db: AsyncSession,
        user_id: str,
        weight_kg: float,
        source: str,
        source_id: Optional[str] = None,
        measured_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Tuple[str, Optional[WeightEntry], bool, Optional[str]]:
        """
        Sync a weight entry from an external source.

        Returns: (status, weight_entry, replan_triggered, revision_id)
            - status: "created" | "deduplicated" | "updated"
            - weight_entry: The created or existing entry
            - replan_triggered: Whether a replan was triggered
            - revision_id: ID of the revision if replan was triggered
        """
        now = datetime.now(timezone.utc)
        measured_at = measured_at or now

        # 1. Check for duplicate by source_id (exact match)
        if source_id:
            existing = await self._find_by_source_id(db, user_id, source, source_id)
            if existing:
                logger.info(
                    "weight_sync_dedupe_source_id",
                    user_id=user_id,
                    source=source,
                    source_id=source_id,
                )
                return "deduplicated", existing, False, None

        # 2. Check for near-duplicate (same source, similar time/weight)
        duplicate = await self._find_near_duplicate(
            db, user_id, source, weight_kg, measured_at
        )
        if duplicate:
            logger.info(
                "weight_sync_dedupe_near",
                user_id=user_id,
                source=source,
                existing_id=duplicate.id,
            )
            return "deduplicated", duplicate, False, None

        # 3. Create new weight entry
        entry = WeightEntry(
            user_id=user_id,
            weight_kg=weight_kg,
            date=measured_at,
            source=source,
            source_id=source_id,
            synced_at=now,
            notes=notes,
        )
        db.add(entry)

        # 4. Update profile weight
        profile = await self._update_profile_weight(db, user_id, weight_kg)

        await db.flush()  # Get the entry ID

        logger.info(
            "weight_sync_created",
            user_id=user_id,
            source=source,
            weight_kg=weight_kg,
            entry_id=entry.id,
        )

        # 5. Evaluate for replan (through normal path, not direct mutation)
        replan_triggered = False
        revision_id = None

        if profile:
            triggered, rev_id = await self._evaluate_replan_trigger(
                db, user_id, profile
            )
            replan_triggered = triggered
            revision_id = rev_id

        return "created", entry, replan_triggered, revision_id

    async def _find_by_source_id(
        self,
        db: AsyncSession,
        user_id: str,
        source: str,
        source_id: str,
    ) -> Optional[WeightEntry]:
        """Find an existing entry by source and source_id."""
        result = await db.execute(
            select(WeightEntry).where(
                and_(
                    WeightEntry.user_id == user_id,
                    WeightEntry.source == source,
                    WeightEntry.source_id == source_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _find_near_duplicate(
        self,
        db: AsyncSession,
        user_id: str,
        source: str,
        weight_kg: float,
        measured_at: datetime,
    ) -> Optional[WeightEntry]:
        """
        Find a near-duplicate entry from the same source.

        Near-duplicate = same source + within time window + similar weight.
        """
        window_start = measured_at - timedelta(minutes=DEDUPE_WINDOW_MINUTES)
        window_end = measured_at + timedelta(minutes=DEDUPE_WINDOW_MINUTES)

        result = await db.execute(
            select(WeightEntry).where(
                and_(
                    WeightEntry.user_id == user_id,
                    WeightEntry.source == source,
                    WeightEntry.date >= window_start,
                    WeightEntry.date <= window_end,
                )
            )
        )
        candidates = result.scalars().all()

        for entry in candidates:
            if abs(entry.weight_kg - weight_kg) <= DEDUPE_WEIGHT_TOLERANCE_KG:
                return entry

        return None

    async def _update_profile_weight(
        self,
        db: AsyncSession,
        user_id: str,
        weight_kg: float,
    ) -> Optional[UserProfile]:
        """Update the user's profile weight."""
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            profile.weight_kg = weight_kg
        return profile

    async def _evaluate_replan_trigger(
        self,
        db: AsyncSession,
        user_id: str,
        profile: UserProfile,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate whether this weight sync should trigger a replan.

        Routes through the normal replanning path - does NOT directly mutate plan.
        Respects existing thresholds, cooldown, and revision state rules.

        Returns: (triggered, revision_id)
        """
        # Get the two most recent weight entries for delta calculation
        result = await db.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(desc(WeightEntry.date))
            .limit(2)
        )
        weights = result.scalars().all()

        if len(weights) < 2:
            return False, None

        weight_delta = weights[0].weight_kg - weights[1].weight_kg

        # Check threshold (from profile or default)
        threshold = profile.replan_weight_threshold_kg or 0.5
        if abs(weight_delta) < threshold:
            return False, None

        # Check cooldown
        cooldown_days = profile.replan_cooldown_days or 3
        result = await db.execute(
            select(PlanRevision.created_at)
            .where(
                PlanRevision.user_id == user_id,
                PlanRevision.status.in_(["pending", "applied", "approved"]),
                or_(
                    PlanRevision.target_area == "nutrition",
                    PlanRevision.target_area == "both",
                ),
            )
            .order_by(desc(PlanRevision.created_at))
            .limit(1)
        )
        last_revision_date = result.scalar_one_or_none()

        if last_revision_date:
            days_since = (datetime.now(timezone.utc) - last_revision_date).days
            if days_since < cooldown_days:
                logger.info(
                    "weight_sync_replan_cooldown",
                    user_id=user_id,
                    days_since=days_since,
                    cooldown_days=cooldown_days,
                )
                return False, None

        # Check if there's an active plan
        result = await db.execute(
            select(WeeklyPlan)
            .where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
            .limit(1)
        )
        plan = result.scalar_one_or_none()
        if not plan:
            return False, None

        # All checks passed - trigger replan through the normal endpoint
        # We return True to indicate replan should be triggered,
        # but the actual replan call happens in the API layer
        logger.info(
            "weight_sync_replan_triggered",
            user_id=user_id,
            weight_delta=weight_delta,
            threshold=threshold,
        )
        return True, None

    async def get_latest_weight(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Optional[dict]:
        """
        Get the latest weight entry with sync metadata.

        Returns dict with:
        - weight_kg, date, source, source_id, synced_at
        - last_sync_time: most recent sync from any external source
        - trend: up | down | stable
        - delta_kg: change from previous entry
        """
        # Get latest entry
        result = await db.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(desc(WeightEntry.date))
            .limit(2)
        )
        entries = result.scalars().all()

        if not entries:
            return None

        latest = entries[0]

        # Calculate trend and delta
        trend = None
        delta_kg = None
        if len(entries) >= 2:
            delta_kg = round(latest.weight_kg - entries[1].weight_kg, 2)
            if delta_kg > 0.1:
                trend = "up"
            elif delta_kg < -0.1:
                trend = "down"
            else:
                trend = "stable"

        # Get last sync time from any external source
        sync_result = await db.execute(
            select(WeightEntry.synced_at)
            .where(
                WeightEntry.user_id == user_id,
                WeightEntry.source != "manual",
                WeightEntry.synced_at.isnot(None),
            )
            .order_by(desc(WeightEntry.synced_at))
            .limit(1)
        )
        last_sync_time = sync_result.scalar_one_or_none()

        return {
            "weight_kg": latest.weight_kg,
            "date": latest.date,
            "source": latest.source,
            "source_id": latest.source_id,
            "synced_at": latest.synced_at,
            "last_sync_time": last_sync_time,
            "trend": trend,
            "delta_kg": delta_kg,
        }
