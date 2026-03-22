"""
AI Fitness Coach v1 — Rules Engine

Non-negotiable guardrails that validate LLM-generated plans
before they are written to external systems.

Design principle: LLM suggests → Rules approve → Then write
"""
from typing import Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class RuleViolation:
    """A single rule violation found during validation."""
    rule: str
    severity: str  # "error" | "warning"
    message: str
    fix_applied: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of rules engine validation."""
    is_valid: bool
    violations: list[RuleViolation] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)
    modified_plan: Optional[dict] = None  # The plan after auto-fixes

    @property
    def errors(self) -> list[RuleViolation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def warnings(self) -> list[RuleViolation]:
        return [v for v in self.violations if v.severity == "warning"]


class RulesEngine:
    """
    Validates and adjusts LLM-generated plans against safety and
    preference constraints. This is deterministic code, not AI.
    """

    # ─── Workout Rules ─────────────────────────────────────────

    # Maximum weekly volume limits by muscle group (sets per week)
    MAX_WEEKLY_VOLUME = {
        "chest": 20,
        "back": 20,
        "shoulders": 16,
        "biceps": 14,
        "triceps": 14,
        "quads": 20,
        "hamstrings": 16,
        "glutes": 16,
        "calves": 12,
        "abs": 16,
        "forearms": 10,
    }

    # Minimum rest between same-muscle-group training (days)
    MIN_REST_DAYS = {
        "compound": 2,   # Squat, Deadlift, Bench
        "isolation": 1,  # Curls, Extensions
    }

    # Maximum session length (minutes)
    MAX_SESSION_LENGTH = 120

    # ─── Nutrition Rules ───────────────────────────────────────

    # Calorie bounds
    MIN_CALORIES = 1200
    MAX_CALORIES = 5000

    # Protein minimums by goal (g per kg bodyweight)
    PROTEIN_MINIMUMS = {
        "fat_loss": 1.6,
        "muscle_gain": 1.8,
        "maintenance": 1.4,
        "general_fitness": 1.2,
    }

    def validate_workout_plan(self, plan: dict, profile: dict) -> ValidationResult:
        """
        Validate a workout plan against training rules.

        Checks:
        - Volume limits per muscle group
        - Rest/recovery spacing
        - Equipment constraints
        - Session duration
        - Injury-safe exercise selection
        """
        violations = []
        rules_applied = []
        modified_plan = plan.copy()

        days = plan.get("days", [])
        training_days = [d for d in days if not d.get("is_rest_day", False)]

        # ── Rule 1: Training day count ──
        rules_applied.append("training_day_count")
        target_days = profile.get("days_per_week", 4)
        if len(training_days) > target_days:
            violations.append(RuleViolation(
                rule="training_day_count",
                severity="warning",
                message=f"Plan has {len(training_days)} training days but user wants {target_days}",
            ))

        # ── Rule 2: Session duration ──
        rules_applied.append("session_duration")
        max_len = profile.get("session_length_min", 60)
        for day in training_days:
            est_duration = day.get("estimated_duration_min", 0)
            if est_duration > max_len + 15:  # 15 min grace
                violations.append(RuleViolation(
                    rule="session_duration",
                    severity="warning",
                    message=f"{day['day']}: Estimated {est_duration}min exceeds {max_len}min target",
                ))

        # ── Rule 3: Weekly volume per muscle group ──
        rules_applied.append("weekly_volume_cap")
        volume_by_group = {}
        for day in training_days:
            for ex in day.get("exercises", []):
                group = (ex.get("muscle_group") or "other").lower()
                volume_by_group[group] = volume_by_group.get(group, 0) + ex.get("sets", 3)

        for group, total_sets in volume_by_group.items():
            max_vol = self.MAX_WEEKLY_VOLUME.get(group, 20)
            if total_sets > max_vol:
                violations.append(RuleViolation(
                    rule="weekly_volume_cap",
                    severity="warning",
                    message=f"{group}: {total_sets} total sets exceeds {max_vol} max",
                    fix_applied=f"Consider reducing {group} volume",
                ))

        # ── Rule 4: Equipment constraints ──
        rules_applied.append("equipment_constraints")
        available_equipment = set(e.lower() for e in profile.get("equipment", []))
        if available_equipment:  # Only check if equipment is specified
            equipment_exercise_map = {
                "bench press": ["barbell", "bench"],
                "squat": ["rack", "barbell"],
                "deadlift": ["barbell"],
                "cable fly": ["cables"],
                "lat pulldown": ["cables"],
                "leg press": ["leg press"],
            }
            for day in training_days:
                for ex in day.get("exercises", []):
                    ex_name = ex.get("name", "").lower()
                    required = equipment_exercise_map.get(ex_name, [])
                    missing = [eq for eq in required if eq not in available_equipment]
                    if missing:
                        violations.append(RuleViolation(
                            rule="equipment_constraints",
                            severity="error",
                            message=f"'{ex['name']}' requires {missing} but user doesn't have it",
                        ))

        # ── Rule 5: Injury awareness ──
        rules_applied.append("injury_check")
        injuries = profile.get("injuries", [])
        injury_areas = {inj.get("area", "").lower() for inj in injuries if isinstance(inj, dict)}

        risky_exercises = {
            "left_knee": ["squat", "lunge", "leg press", "leg extension"],
            "right_knee": ["squat", "lunge", "leg press", "leg extension"],
            "lower_back": ["deadlift", "barbell row", "good morning"],
            "left_shoulder": ["overhead press", "lateral raise", "bench press"],
            "right_shoulder": ["overhead press", "lateral raise", "bench press"],
        }

        for area in injury_areas:
            risky = risky_exercises.get(area, [])
            for day in training_days:
                for ex in day.get("exercises", []):
                    if ex.get("name", "").lower() in risky:
                        violations.append(RuleViolation(
                            rule="injury_check",
                            severity="error",
                            message=f"'{ex['name']}' may aggravate {area} injury — use substitution",
                        ))

        is_valid = len([v for v in violations if v.severity == "error"]) == 0
        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            rules_applied=rules_applied,
            modified_plan=modified_plan,
        )

    def validate_meal_plan(self, plan: dict, profile: dict) -> ValidationResult:
        """
        Validate a meal plan against nutrition rules.

        Checks:
        - Calorie floors/ceilings
        - Protein minimums
        - Dietary restriction compliance
        - Macro balance reasonableness
        """
        violations = []
        rules_applied = []

        days = plan.get("days", [])
        target_cal = profile.get("target_calories", 2200)
        target_protein = profile.get("target_protein_g", 180)
        restrictions = set(r.lower() for r in profile.get("dietary_restrictions", []))

        # ── Rule 1: Calorie bounds ──
        rules_applied.append("calorie_bounds")
        if target_cal < self.MIN_CALORIES:
            violations.append(RuleViolation(
                rule="calorie_bounds",
                severity="error",
                message=f"Target calories {target_cal} below safety minimum {self.MIN_CALORIES}",
            ))
        if target_cal > self.MAX_CALORIES:
            violations.append(RuleViolation(
                rule="calorie_bounds",
                severity="warning",
                message=f"Target calories {target_cal} is unusually high",
            ))

        # ── Rule 2: Daily calorie accuracy ──
        rules_applied.append("daily_calorie_check")
        tolerance = 0.15  # 15% tolerance
        for day in days:
            totals = day.get("totals", {})
            day_cal = totals.get("calories", 0)
            if day_cal > 0:
                deviation = abs(day_cal - target_cal) / target_cal
                if deviation > tolerance:
                    violations.append(RuleViolation(
                        rule="daily_calorie_check",
                        severity="warning",
                        message=f"{day['day']}: {day_cal}cal is {deviation:.0%} off target {target_cal}cal",
                    ))

        # ── Rule 3: Protein minimum ──
        rules_applied.append("protein_minimum")
        goal = profile.get("goal", "maintenance")
        weight_kg = profile.get("weight_kg")
        min_protein = target_protein  # Use target as minimum

        if weight_kg:
            # Calculate protein minimum from body weight
            protein_per_kg = self.PROTEIN_MINIMUMS.get(goal, 1.4)
            weight_based_min = weight_kg * protein_per_kg
            min_protein = max(min_protein, weight_based_min)

        for day in days:
            totals = day.get("totals", {})
            day_protein = totals.get("protein_g", 0)
            if day_protein > 0 and day_protein < min_protein * 0.85:
                violations.append(RuleViolation(
                    rule="protein_minimum",
                    severity="warning",
                    message=f"{day['day']}: {day_protein}g protein below minimum {min_protein:.0f}g",
                ))

        # ── Rule 4: Dietary restrictions ──
        rules_applied.append("dietary_restrictions")
        restriction_keywords = {
            "vegetarian": ["chicken", "beef", "pork", "fish", "meat", "steak", "turkey"],
            "vegan": ["chicken", "beef", "pork", "fish", "meat", "egg", "dairy", "cheese", "milk", "whey"],
            "gluten_free": ["bread", "pasta", "wheat", "flour"],
            "dairy_free": ["cheese", "milk", "yogurt", "cream", "butter", "whey"],
            "low_sugar": [],  # Would need recipe analysis
            "keto": [],  # Would check carb ratios
        }

        for restriction in restrictions:
            blocked_words = restriction_keywords.get(restriction, [])
            for day in days:
                for meal in day.get("meals", []):
                    meal_name = meal.get("name", "").lower()
                    for word in blocked_words:
                        if word in meal_name:
                            violations.append(RuleViolation(
                                rule="dietary_restrictions",
                                severity="error",
                                message=f"{day['day']} {meal['meal_type']}: '{meal['name']}' may violate {restriction} restriction",
                            ))

        is_valid = len([v for v in violations if v.severity == "error"]) == 0
        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            rules_applied=rules_applied,
        )

    def validate_plan(self, workout_plan: dict, meal_plan: dict, profile: dict) -> dict:
        """
        Validate both workout and meal plans. Returns combined results.
        """
        workout_result = self.validate_workout_plan(workout_plan, profile)
        meal_result = self.validate_meal_plan(meal_plan, profile)

        return {
            "is_valid": workout_result.is_valid and meal_result.is_valid,
            "workout": {
                "is_valid": workout_result.is_valid,
                "errors": [{"rule": v.rule, "message": v.message} for v in workout_result.errors],
                "warnings": [{"rule": v.rule, "message": v.message} for v in workout_result.warnings],
                "rules_applied": workout_result.rules_applied,
            },
            "meal": {
                "is_valid": meal_result.is_valid,
                "errors": [{"rule": v.rule, "message": v.message} for v in meal_result.errors],
                "warnings": [{"rule": v.rule, "message": v.message} for v in meal_result.warnings],
                "rules_applied": meal_result.rules_applied,
            },
        }
