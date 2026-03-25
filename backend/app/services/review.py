"""
AI Fitness Coach v1 — Weekly Review Service

Generates aggregated analytics and insights for weekly progress review.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from app.models.user import UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, WorkoutLog, AdherenceRecord, PlanRevision
from app.schemas.review import (
    WeeklyReviewResponse,
    WeightSummary,
    WorkoutSummary,
    NutritionSummary,
    CoachAdjustment,
    TrendsResponse,
    TrendsSummary,
    WeightTrends,
    WorkoutTrends,
    NutritionTrends,
    WeekWeightPoint,
    WeekWorkoutPoint,
    WeekNutritionPoint,
    RevisionFrequency,
    GoalAlignment,
)
from app.logging_config import get_logger

logger = get_logger("review_service")


class WeeklyReviewService:
    """
    Generates weekly analytics including:
    - Weight trend analysis
    - Workout completion metrics
    - Nutrition adherence
    - Coach adjustment summary
    - Rule-based insights
    """

    def __init__(self):
        pass

    async def generate_weekly_review(
        self,
        db: AsyncSession,
        user_id: str,
        week_offset: int = 0,
    ) -> WeeklyReviewResponse:
        """
        Generate a complete weekly review.

        Args:
            db: Database session
            user_id: User ID
            week_offset: 0 = current week, -1 = last week, etc.
        """
        # Calculate week boundaries
        today = datetime.now(timezone.utc)
        week_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start -= timedelta(days=today.weekday())  # Monday
        week_start += timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        # Load profile
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()

        if not profile:
            return WeeklyReviewResponse(
                week_start=week_start.strftime("%Y-%m-%d"),
                week_end=week_end.strftime("%Y-%m-%d"),
                weight=WeightSummary(),
                workouts=WorkoutSummary(),
                nutrition=NutritionSummary(),
                message="No profile found. Complete your profile to get started.",
            )

        # Load active plan
        plan_result = await db.execute(
            select(WeeklyPlan)
            .where(WeeklyPlan.user_id == user_id, WeeklyPlan.status == "active")
            .order_by(desc(WeeklyPlan.created_at))
            .limit(1)
        )
        plan = plan_result.scalar_one_or_none()

        # Calculate each section
        weight_summary = await self._calculate_weight_trend(db, user_id, profile.goal)
        workout_summary = await self._calculate_workout_metrics(
            db, user_id, plan, week_start, week_end
        )
        nutrition_summary = await self._calculate_nutrition_metrics(
            db, user_id, profile, week_start, week_end
        )
        adjustments = await self._summarize_adjustments(db, plan)

        # Generate insights
        insights = self._generate_insights(
            profile.goal,
            weight_summary,
            workout_summary,
            nutrition_summary,
            adjustments,
        )
        next_action = self._get_next_action(
            profile.goal, plan, workout_summary, nutrition_summary
        )

        # Determine if there's a message for empty states
        message = None
        if not plan:
            message = "No active plan. Generate a weekly plan to start tracking."

        return WeeklyReviewResponse(
            week_start=week_start.strftime("%Y-%m-%d"),
            week_end=week_end.strftime("%Y-%m-%d"),
            goal=profile.goal,
            weight=weight_summary,
            workouts=workout_summary,
            nutrition=nutrition_summary,
            coach_adjustments=adjustments,
            insights=insights,
            next_action=next_action,
            message=message,
        )

    async def _calculate_weight_trend(
        self,
        db: AsyncSession,
        user_id: str,
        goal: str,
    ) -> WeightSummary:
        """Calculate weight trend from last 14 days."""
        # Get last 14 days of weight entries
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        result = await db.execute(
            select(WeightEntry)
            .where(
                WeightEntry.user_id == user_id,
                WeightEntry.date >= cutoff,
            )
            .order_by(desc(WeightEntry.date))
        )
        entries = result.scalars().all()

        if len(entries) < 2:
            return WeightSummary()

        # Get start and current weight
        oldest = min(entries, key=lambda e: e.date)
        newest = max(entries, key=lambda e: e.date)

        start_kg = round(oldest.weight_kg, 1)
        current_kg = round(newest.weight_kg, 1)
        change_kg = round(current_kg - start_kg, 1)

        # Determine trend
        if abs(change_kg) < 0.2:
            trend = "stable"
        elif change_kg < 0:
            trend = "losing"
        else:
            trend = "gaining"

        # Check alignment with goal
        alignment = {
            "fat_loss": trend in ("losing", "stable"),
            "muscle_gain": trend in ("gaining", "stable"),
            "maintenance": trend == "stable",
            "general_fitness": True,
        }
        aligned = alignment.get(goal, True)

        return WeightSummary(
            start_kg=start_kg,
            current_kg=current_kg,
            change_kg=change_kg,
            trend=trend,
            aligned_with_goal=aligned,
        )

    async def _calculate_workout_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        plan: Optional[WeeklyPlan],
        week_start: datetime,
        week_end: datetime,
    ) -> WorkoutSummary:
        """Calculate workout completion for the week."""
        # Count planned workouts from the plan
        planned = 0
        if plan and plan.workout_plan:
            wp = plan.workout_plan
            workout_days = wp if isinstance(wp, list) else wp.get("days", [])
            planned = len([d for d in workout_days if not d.get("is_rest_day", False)])

        # Get workout logs for the week
        result = await db.execute(
            select(WorkoutLog)
            .where(
                WorkoutLog.user_id == user_id,
                WorkoutLog.date >= week_start,
                WorkoutLog.date <= week_end,
            )
            .order_by(desc(WorkoutLog.date))
        )
        logs = result.scalars().all()

        completed = len(logs)
        completion_pct = (completed / planned * 100) if planned > 0 else 0.0

        # Calculate averages
        total_duration = sum(log.duration_min or 0 for log in logs)
        energy_levels = [log.energy_level for log in logs if log.energy_level is not None]
        avg_energy = round(sum(energy_levels) / len(energy_levels), 1) if energy_levels else None

        return WorkoutSummary(
            planned=planned,
            completed=completed,
            completion_pct=round(completion_pct, 1),
            avg_energy=avg_energy,
            total_duration_min=total_duration,
        )

    async def _calculate_nutrition_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        profile: UserProfile,
        week_start: datetime,
        week_end: datetime,
    ) -> NutritionSummary:
        """Calculate nutrition adherence for the week."""
        # Get adherence records for the week
        result = await db.execute(
            select(AdherenceRecord)
            .where(
                AdherenceRecord.user_id == user_id,
                AdherenceRecord.date >= week_start,
                AdherenceRecord.date <= week_end,
            )
            .order_by(AdherenceRecord.date)
        )
        records = result.scalars().all()

        # Calculate days in the week so far
        now = datetime.now(timezone.utc)
        if now < week_end:
            total_days = (now.date() - week_start.date()).days + 1
        else:
            total_days = 7

        if not records:
            return NutritionSummary(
                total_days=total_days,
                target_calories=profile.target_calories,
            )

        # Count days where meals were followed
        days_on_target = 0
        total_calories = 0
        calories_count = 0

        for rec in records:
            if rec.meals_followed and rec.meals_planned:
                if rec.meals_followed >= rec.meals_planned * 0.8:  # 80% threshold
                    days_on_target += 1
            if rec.calories_actual:
                total_calories += rec.calories_actual
                calories_count += 1

        adherence_pct = (days_on_target / len(records) * 100) if records else 0.0
        avg_calories = int(total_calories / calories_count) if calories_count > 0 else None

        return NutritionSummary(
            days_on_target=days_on_target,
            total_days=total_days,
            adherence_pct=round(adherence_pct, 1),
            avg_calories=avg_calories,
            target_calories=profile.target_calories,
        )

    async def _summarize_adjustments(
        self,
        db: AsyncSession,
        plan: Optional[WeeklyPlan],
    ) -> list[CoachAdjustment]:
        """Summarize plan revisions / coach adjustments."""
        if not plan:
            return []

        result = await db.execute(
            select(PlanRevision)
            .where(PlanRevision.plan_id == plan.id)
            .order_by(desc(PlanRevision.created_at))
        )
        revisions = result.scalars().all()

        adjustments = []
        for rev in revisions:
            # Build human-readable change description
            change_parts = []
            patch = rev.patch or {}

            # Check for calorie adjustments
            cal_adjust = patch.get("meal_plan", {}).get("calorie_adjust", 0)
            if cal_adjust != 0:
                sign = "+" if cal_adjust > 0 else ""
                change_parts.append(f"calories {sign}{cal_adjust}")

            # Check for volume adjustments
            vol_modifier = patch.get("workout_plan", {}).get("global_modifier", 0)
            if vol_modifier != 0:
                pct = int(vol_modifier * 100)
                sign = "+" if pct > 0 else ""
                change_parts.append(f"volume {sign}{pct}%")

            change_str = ", ".join(change_parts) if change_parts else rev.trigger.replace("_", " ")

            adjustments.append(
                CoachAdjustment(
                    trigger=rev.trigger,
                    area=rev.target_area,
                    change=change_str,
                    status=rev.status,
                    date=rev.created_at.strftime("%Y-%m-%d"),
                )
            )

        return adjustments

    def _generate_insights(
        self,
        goal: str,
        weight: WeightSummary,
        workouts: WorkoutSummary,
        nutrition: NutritionSummary,
        adjustments: list[CoachAdjustment],
    ) -> list[str]:
        """Generate rule-based insights from the data."""
        insights = []

        # Weight insight
        if weight.trend and weight.aligned_with_goal is not None:
            if weight.aligned_with_goal:
                if goal == "fat_loss" and weight.trend == "losing":
                    insights.append(
                        f"Weight trending down ({weight.change_kg:+.1f} kg) - on track for fat loss"
                    )
                elif goal == "muscle_gain" and weight.trend == "gaining":
                    insights.append(
                        f"Weight trending up ({weight.change_kg:+.1f} kg) - supporting muscle gain"
                    )
                elif weight.trend == "stable":
                    insights.append("Weight stable - maintaining current composition")
            else:
                if goal == "fat_loss" and weight.trend == "gaining":
                    insights.append(
                        "Weight trending up while targeting fat loss - review calorie intake"
                    )
                elif goal == "muscle_gain" and weight.trend == "losing":
                    insights.append(
                        "Weight trending down while targeting muscle gain - increase calories"
                    )

        # Check if adjustments are helping
        active_adjustments = [a for a in adjustments if a.status in ("applied", "approved")]
        if active_adjustments and weight.aligned_with_goal:
            cal_adjust = next(
                (a for a in active_adjustments if "calories" in a.change.lower()),
                None
            )
            if cal_adjust:
                insights.append(f"Recent {cal_adjust.change} adjustment appears to be helping")

        # Workout consistency
        if workouts.planned > 0:
            if workouts.completion_pct >= 75:
                insights.append(
                    f"{workouts.completed}/{workouts.planned} workouts completed - great consistency"
                )
            elif workouts.completion_pct >= 50:
                insights.append(
                    f"{workouts.completed}/{workouts.planned} workouts completed - room for improvement"
                )
            else:
                insights.append(
                    f"Only {workouts.completed}/{workouts.planned} workouts completed - prioritize training"
                )

        # Energy levels
        if workouts.avg_energy is not None:
            if workouts.avg_energy < 2.5:
                insights.append(
                    f"Low average energy ({workouts.avg_energy}/5) - consider recovery focus"
                )
            elif workouts.avg_energy >= 4:
                insights.append(
                    f"High energy levels ({workouts.avg_energy}/5) - training is sustainable"
                )

        # Nutrition adherence
        if nutrition.total_days > 0:
            if nutrition.adherence_pct >= 80:
                insights.append(
                    f"Nutrition adherence at {nutrition.adherence_pct:.0f}% - excellent"
                )
            elif nutrition.adherence_pct >= 60:
                insights.append(
                    f"Nutrition adherence at {nutrition.adherence_pct:.0f}% - consider meal prep"
                )
            elif nutrition.adherence_pct > 0:
                insights.append(
                    f"Nutrition adherence at {nutrition.adherence_pct:.0f}% - significant opportunity to improve"
                )

        return insights

    def _get_next_action(
        self,
        goal: str,
        plan: Optional[WeeklyPlan],
        workouts: WorkoutSummary,
        nutrition: NutritionSummary,
    ) -> Optional[str]:
        """Determine the recommended next action."""
        if not plan:
            return "Generate your first weekly plan to get started"

        # If workouts are low, prioritize that
        if workouts.planned > 0 and workouts.completion_pct < 50:
            remaining = workouts.planned - workouts.completed
            return f"Complete {remaining} more workout(s) this week to stay on track"

        # If nutrition is low, suggest that
        if nutrition.total_days > 0 and nutrition.adherence_pct < 60:
            return "Focus on meal adherence today - prep your meals in advance"

        # Default positive action
        if goal == "fat_loss":
            return "Stay consistent with your plan - progress is showing"
        elif goal == "muscle_gain":
            return "Keep pushing - consistent training drives muscle growth"

        return "Keep up the good work - consistency is key"

    # --- Trends Methods ---

    async def generate_trends(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> TrendsResponse:
        """
        Generate 4-week trend analysis.

        Aggregates weekly reviews for the last 4 weeks and calculates:
        - Weight trend direction
        - Workout completion trend
        - Nutrition adherence trend
        - Revision frequency
        - Goal alignment status
        """
        # Load profile for goal
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()

        if not profile:
            return TrendsResponse(
                user_id=user_id,
                trends=TrendsSummary(
                    weight=WeightTrends(),
                    workouts=WorkoutTrends(),
                    nutrition=NutritionTrends(),
                ),
                revision_frequency=RevisionFrequency(),
                goal_alignment=GoalAlignment(),
                message="No profile found. Complete your profile to get started.",
            )

        # Get 4 weeks of reviews (oldest to newest for consistent ordering)
        weekly_reviews = []
        for offset in range(-3, 1):  # -3, -2, -1, 0
            review = await self.generate_weekly_review(db, user_id, week_offset=offset)
            weekly_reviews.append(review)

        # Build trend summaries
        weight_trends = self._build_weight_trends(weekly_reviews, profile.goal)
        workout_trends = self._build_workout_trends(weekly_reviews)
        nutrition_trends = self._build_nutrition_trends(weekly_reviews)

        # Get revision frequency
        revision_freq = await self._get_revision_frequency(db, user_id)

        # Calculate goal alignment
        goal_alignment = self._calculate_goal_alignment(
            profile.goal, weekly_reviews
        )

        return TrendsResponse(
            user_id=user_id,
            goal=profile.goal,
            trends=TrendsSummary(
                weight=weight_trends,
                workouts=workout_trends,
                nutrition=nutrition_trends,
            ),
            revision_frequency=revision_freq,
            goal_alignment=goal_alignment,
        )

    def _build_weight_trends(
        self,
        reviews: list[WeeklyReviewResponse],
        goal: str,
    ) -> WeightTrends:
        """Build 4-week weight trends from reviews."""
        weeks = []
        changes = []

        for review in reviews:
            aligned = None
            if review.weight.trend:
                # Check alignment with goal
                alignment = {
                    "fat_loss": review.weight.trend in ("losing", "stable"),
                    "muscle_gain": review.weight.trend in ("gaining", "stable"),
                    "maintenance": review.weight.trend == "stable",
                    "general_fitness": True,
                }
                aligned = alignment.get(goal, True)

            weeks.append(
                WeekWeightPoint(
                    week=review.week_start,
                    change_kg=review.weight.change_kg,
                    trend=review.weight.trend,
                    aligned=aligned,
                )
            )
            if review.weight.change_kg is not None:
                changes.append(review.weight.change_kg)

        total_change = sum(changes) if changes else None
        direction = self._calculate_direction(changes, threshold=0.2)

        return WeightTrends(
            weeks=weeks,
            total_change_kg=round(total_change, 1) if total_change is not None else None,
            direction=direction,
        )

    def _build_workout_trends(
        self,
        reviews: list[WeeklyReviewResponse],
    ) -> WorkoutTrends:
        """Build 4-week workout trends from reviews."""
        weeks = []
        completions = []

        for review in reviews:
            weeks.append(
                WeekWorkoutPoint(
                    week=review.week_start,
                    completion_pct=review.workouts.completion_pct,
                    completed=review.workouts.completed,
                    planned=review.workouts.planned,
                )
            )
            if review.workouts.planned > 0:
                completions.append(review.workouts.completion_pct)

        avg_completion = sum(completions) / len(completions) if completions else 0.0
        direction = self._calculate_direction(completions, threshold=10.0)

        return WorkoutTrends(
            weeks=weeks,
            avg_completion_pct=round(avg_completion, 1),
            direction=direction,
        )

    def _build_nutrition_trends(
        self,
        reviews: list[WeeklyReviewResponse],
    ) -> NutritionTrends:
        """Build 4-week nutrition trends from reviews."""
        weeks = []
        adherences = []

        for review in reviews:
            weeks.append(
                WeekNutritionPoint(
                    week=review.week_start,
                    adherence_pct=review.nutrition.adherence_pct,
                )
            )
            if review.nutrition.total_days > 0:
                adherences.append(review.nutrition.adherence_pct)

        avg_adherence = sum(adherences) / len(adherences) if adherences else 0.0
        direction = self._calculate_direction(adherences, threshold=10.0)

        return NutritionTrends(
            weeks=weeks,
            avg_adherence_pct=round(avg_adherence, 1),
            direction=direction,
        )

    def _calculate_direction(
        self,
        values: list[float],
        threshold: float,
    ) -> str:
        """Calculate trend direction from weekly values."""
        if len(values) < 2:
            return "insufficient_data"

        # Compare first half average to second half average
        mid = len(values) // 2
        first_half = values[:mid] if mid > 0 else values[:1]
        second_half = values[mid:] if mid > 0 else values[1:]

        if not first_half or not second_half:
            return "insufficient_data"

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        change = second_avg - first_avg

        if abs(change) < threshold:
            return "stable"
        return "up" if change > 0 else "down"

    async def _get_revision_frequency(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> RevisionFrequency:
        """Get revision frequency stats for the last 4 weeks."""
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=4)

        result = await db.execute(
            select(PlanRevision)
            .where(
                PlanRevision.user_id == user_id,
                PlanRevision.created_at >= cutoff,
            )
        )
        revisions = result.scalars().all()

        total = len(revisions)
        auto_applied = len([r for r in revisions if r.is_auto_applied and r.status == "applied"])
        user_approved = len([r for r in revisions if r.status == "approved"])
        undone = len([r for r in revisions if r.status == "reverted"])
        superseded = len([r for r in revisions if r.status == "superseded"])

        # Determine assessment
        if total <= 1:
            assessment = "stable"
        elif total <= 4:
            assessment = "moderate"
        else:
            assessment = "active"

        return RevisionFrequency(
            total=total,
            auto_applied=auto_applied,
            user_approved=user_approved,
            undone=undone,
            superseded=superseded,
            assessment=assessment,
        )

    def _calculate_goal_alignment(
        self,
        goal: str,
        reviews: list[WeeklyReviewResponse],
    ) -> GoalAlignment:
        """Calculate goal alignment from weekly reviews."""
        weight_aligned = 0
        workout_target = 0
        nutrition_target = 0

        for review in reviews:
            # Weight alignment
            if review.weight.aligned_with_goal:
                weight_aligned += 1

            # Workout target (>= 75% completion)
            if review.workouts.planned > 0 and review.workouts.completion_pct >= 75:
                workout_target += 1

            # Nutrition target (>= 70% adherence)
            if review.nutrition.total_days > 0 and review.nutrition.adherence_pct >= 70:
                nutrition_target += 1

        # Calculate overall status
        total_aligned = weight_aligned + workout_target + nutrition_target
        total_possible = len(reviews) * 3  # 4 weeks × 3 metrics = 12

        if total_possible == 0:
            status = "insufficient_data"
        else:
            ratio = total_aligned / total_possible
            if ratio >= 0.7:
                status = "on_track"
            elif ratio >= 0.4:
                status = "mixed"
            else:
                status = "off_track"

        return GoalAlignment(
            status=status,
            weight_aligned_weeks=weight_aligned,
            workout_target_weeks=workout_target,
            nutrition_target_weeks=nutrition_target,
        )
