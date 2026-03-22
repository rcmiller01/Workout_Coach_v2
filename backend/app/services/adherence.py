"""
AI Fitness Coach v1 — Adherence Service

Tracks workout and nutrition adherence, detecting patterns
that should trigger adaptive replanning.
"""
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AdherenceSnapshot:
    """Point-in-time adherence metrics."""
    workout_adherence_pct: float = 0.0
    nutrition_adherence_pct: float = 0.0
    streak_days: int = 0
    missed_workouts_this_week: int = 0
    weight_change_7d: Optional[float] = None
    avg_energy_level: Optional[float] = None
    needs_replanning: bool = False
    replanning_reasons: list = None

    def __post_init__(self):
        if self.replanning_reasons is None:
            self.replanning_reasons = []


class AdherenceService:
    """
    Tracks adherence and determines when adaptive replanning is needed.

    Triggers for replanning:
    - 2+ missed workouts in a week
    - Adherence drops below 60%
    - Body weight changes >2% in a week
    - User-reported low energy for 3+ days
    """

    ADHERENCE_THRESHOLD = 0.60
    WEIGHT_CHANGE_THRESHOLD = 0.02  # 2% body weight
    LOW_ENERGY_STREAK = 3

    def calculate_adherence(
        self,
        workout_logs: list,
        planned_workouts: int,
        nutrition_logs: Optional[list] = None,
        planned_meals: int = 0,
    ) -> AdherenceSnapshot:
        """
        Calculate current adherence metrics.
        """
        # Workout adherence
        completed = len(workout_logs)
        workout_pct = (completed / planned_workouts * 100) if planned_workouts > 0 else 0

        # Nutrition adherence
        nutrition_pct = 0
        if planned_meals > 0 and nutrition_logs:
            followed = len([log for log in nutrition_logs if log.get("followed")])
            nutrition_pct = (followed / planned_meals * 100)

        # Missed workouts this week
        missed = max(0, planned_workouts - completed)

        # Energy level
        energy_levels = [
            log.get("energy_level") for log in workout_logs
            if log.get("energy_level") is not None
        ]
        avg_energy = sum(energy_levels) / len(energy_levels) if energy_levels else None

        # Streak calculation
        streak = 0
        # Simple: count consecutive days with logged activity
        if workout_logs:
            sorted_logs = sorted(
                workout_logs,
                key=lambda x: x.get("date", ""),
                reverse=True,
            )
            last_date = None
            for log in sorted_logs:
                log_date = log.get("date")
                if isinstance(log_date, str):
                    try:
                        log_date = datetime.fromisoformat(log_date).date()
                    except (ValueError, TypeError):
                        continue
                elif isinstance(log_date, datetime):
                    log_date = log_date.date()
                else:
                    continue

                if last_date is None:
                    streak = 1
                    last_date = log_date
                elif (last_date - log_date).days <= 2:  # Allow 1 rest day gap
                    streak += 1
                    last_date = log_date
                else:
                    break

        # Determine replanning needs
        needs_replanning = False
        reasons = []

        if missed >= 2:
            needs_replanning = True
            reasons.append(f"Missed {missed} workouts this week")

        if planned_workouts > 0 and workout_pct < self.ADHERENCE_THRESHOLD * 100:
            needs_replanning = True
            reasons.append(f"Workout adherence at {workout_pct:.0f}%")

        if avg_energy is not None and avg_energy < 2.5:
            needs_replanning = True
            reasons.append(f"Low average energy ({avg_energy:.1f}/5)")

        return AdherenceSnapshot(
            workout_adherence_pct=workout_pct,
            nutrition_adherence_pct=nutrition_pct,
            streak_days=streak,
            missed_workouts_this_week=missed,
            avg_energy_level=avg_energy,
            needs_replanning=needs_replanning,
            replanning_reasons=reasons,
        )

    def check_weight_trend(
        self,
        weight_entries: list,
        goal: str,
    ) -> dict:
        """
        Analyze weight trend and determine if it aligns with the goal.
        """
        if len(weight_entries) < 3:
            return {"trend": "insufficient_data", "aligned_with_goal": None}

        # Calculate 7-day moving average
        recent = [float(e.get("weight", 0)) for e in weight_entries[:7]]
        older = [float(e.get("weight", 0)) for e in weight_entries[7:14]]

        if not older:
            older = recent

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        change = recent_avg - older_avg
        change_pct = change / older_avg if older_avg > 0 else 0

        if abs(change_pct) < 0.005:
            trend = "stable"
        elif change_pct > 0:
            trend = "gaining"
        else:
            trend = "losing"

        # Check alignment with goal
        goal_alignment = {
            "fat_loss": trend == "losing",
            "muscle_gain": trend in ("gaining", "stable"),
            "maintenance": trend == "stable",
            "general_fitness": True,
        }
        aligned = goal_alignment.get(goal, True)

        return {
            "trend": trend,
            "change_kg": round(change, 2),
            "change_pct": round(change_pct * 100, 2),
            "aligned_with_goal": aligned,
            "recommendation": self._weight_recommendation(trend, goal, change),
        }

    @staticmethod
    def _weight_recommendation(trend: str, goal: str, change_kg: float) -> str:
        """Generate a recommendation based on weight trend vs goal."""
        if goal == "fat_loss":
            if trend == "losing" and abs(change_kg) <= 1.0:
                return "On track. Healthy rate of loss."
            elif trend == "losing" and abs(change_kg) > 1.0:
                return "Losing too fast. Consider increasing calories slightly."
            elif trend == "stable":
                return "Weight stable. May need to adjust calories down or activity up."
            else:
                return "Gaining while targeting fat loss. Review nutrition adherence."

        elif goal == "muscle_gain":
            if trend == "gaining" and change_kg <= 0.5:
                return "On track. Healthy lean gain rate."
            elif trend == "gaining" and change_kg > 0.5:
                return "Gaining quickly. May need to reduce surplus slightly."
            elif trend == "stable":
                return "Weight stable. Consider increasing calories by 200-300."
            else:
                return "Losing while targeting muscle gain. Increase calories."

        return "Monitor and adjust as needed."
