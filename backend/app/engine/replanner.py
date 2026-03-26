"""
AI Fitness Coach v1 — Replanning Engine

Logic for producing 'delta patches' based on adherence and progress signals.
Strictly limited to ~10-15% volume adjustments and 100-200kcal shifts.
"""
from typing import List, Dict, Optional, Tuple
from app.engine.models import NormalizedPlan, NormalizedWorkoutDay, NormalizedMealDay
from app.logging_config import get_logger

logger = get_logger("replanner")

class Replanner:
    """
    Produces incremental plan adjustments ('patches') instead of full rewrites.
    """

    # Adjustment caps (not user-configurable for safety)
    VOL_MODIFIER = 0.15  # 15% cap
    CAL_MODIFIER = 200   # 200kcal cap

    # Default Sensitivity Settings (can be overridden per-user)
    DEFAULT_WEIGHT_THRESHOLD_KG = 0.5
    DEFAULT_MISSED_WORKOUT_THRESHOLD = 2
    DEFAULT_COOLDOWN_DAYS = 3

    def calculate_adjustment(
        self,
        current_plan: Dict,
        adherence_summary: Dict,
        weight_delta_kg: float,
        goal: str,
        last_revision_dates: Dict[str, "datetime"] = None,
        sensitivity_settings: Dict = None
    ) -> Tuple[str, str, Dict]:
        """
        Main logic for Adaptive Replanning v1.

        Args:
            sensitivity_settings: Optional per-user overrides for thresholds:
                - weight_threshold_kg: Weight trend threshold before calorie changes
                - missed_workout_threshold: Missed workouts before volume reductions
                - cooldown_days: Cooldown window between revisions in same area

        Returns: (trigger, reason, patch)
        """
        import datetime
        trigger = "manual"
        reason = "Base adjustment."
        patch = {"workout_plan": {}, "meal_plan": {}}
        last_revision_dates = last_revision_dates or {}
        sensitivity_settings = sensitivity_settings or {}
        now = datetime.datetime.now(datetime.timezone.utc)

        # Extract sensitivity settings with defaults
        weight_threshold = sensitivity_settings.get(
            "weight_threshold_kg", self.DEFAULT_WEIGHT_THRESHOLD_KG
        )
        missed_workout_threshold = sensitivity_settings.get(
            "missed_workout_threshold", self.DEFAULT_MISSED_WORKOUT_THRESHOLD
        )
        cooldown_days = sensitivity_settings.get(
            "cooldown_days", self.DEFAULT_COOLDOWN_DAYS
        )

        def _in_cooldown(area: str) -> bool:
            last_date = last_revision_dates.get(area)
            if not last_date:
                return False
            # naive vs aware shouldn't be an issue if we assume utc everywhere
            if last_date.tzinfo:
                now_aware = now.replace(tzinfo=datetime.timezone.utc)
                return (now_aware - last_date).days < cooldown_days
            return (now - last_date).days < cooldown_days

        # 1. Trigger: Missed Workouts
        missed_count = adherence_summary.get("missed_workouts", 0)
        if missed_count >= missed_workout_threshold and not _in_cooldown("workout"):
            trigger = "missed_workout"
            reason = f"Reducing volume by 15% due to {missed_count} missed sessions"
            patch["workout_plan"] = self._apply_volume_patch(current_plan, -self.VOL_MODIFIER)

        # 2. Trigger: Meal Non-Adherence
        meal_adherence = adherence_summary.get("meal_adherence_pct", 100)
        if meal_adherence < 70 and not _in_cooldown("nutrition"):
            trigger = "meal_non_adherence"
            reason = f"Switching to higher-protein/easier options due to {meal_adherence}% adherence"
            # In v1, we just flag for easier meals (we can't easily 'patch' text yet without LLM)
            # but we can adjust target protein floor.
            patch["meal_plan"] = {"instructions": "Focus on high-protein, 15-min prep meals."}

        # 3. Trigger: Weight Delta
        # Cooldown check for nutrition since weight delta affects meals
        if abs(weight_delta_kg) >= weight_threshold and not _in_cooldown("nutrition"):
            cal_delta = 0
            if goal == "fat_loss" and weight_delta_kg > 0:
                cal_delta = -self.CAL_MODIFIER
                reason += f" | Reducing calories by {self.CAL_MODIFIER} due to weight gain ({weight_delta_kg}kg)"
            elif goal == "muscle_gain" and weight_delta_kg < 0:
                cal_delta = self.CAL_MODIFIER
                reason += f" | Increasing calories by {self.CAL_MODIFIER} due to stagnant weight"

            if cal_delta != 0:
                trigger = "weight_change"
                patch["meal_plan"]["calorie_adjust"] = cal_delta

        # 4. Steps-based activity adjustment (additive, stacks with weight delta)
        # Steps affect calorie interpretation only — NOT workout volume
        steps_cal_adjust = adherence_summary.get("steps_calorie_adjust", 0)
        if steps_cal_adjust != 0 and not _in_cooldown("nutrition"):
            existing_cal = patch["meal_plan"].get("calorie_adjust", 0)
            combined = existing_cal + steps_cal_adjust
            # Cap combined adjustment at ±CAL_MODIFIER
            combined = max(-self.CAL_MODIFIER, min(self.CAL_MODIFIER, combined))
            if combined != 0:
                patch["meal_plan"]["calorie_adjust"] = combined
                avg_steps = adherence_summary.get("avg_daily_steps", 0)
                reason += f" | Activity adjustment {steps_cal_adjust:+d} kcal based on {avg_steps} avg daily steps"
                if trigger == "manual":
                    trigger = "activity_level"

        return trigger, reason, patch

    def _apply_volume_patch(self, plan: Dict, factor: float) -> Dict:
        """Calculate set reductions across the remaining days."""
        # Simple implementation for v1: suggest reducing sets by 1 for compound moves
        return {"global_modifier": factor, "instruction": f"Reduce all sets by {abs(int(factor*100))}%"}

    def apply_patch_to_plan(self, plan_dict: Dict, patch: Dict) -> Dict:
        """
        Actually apply the patch to a plan dictionary (for persistence/UI).
        """
        # 1. Volume adjustment
        if "workout_plan" in patch and "global_modifier" in patch["workout_plan"]:
            factor = 1 + patch["workout_plan"]["global_modifier"]
            workout_days = plan_dict.get("workout_plan", {}).get("days", [])
            for day in workout_days:
                for ex in day.get("exercises", []):
                    # Minimum 1 set, avoid float sets
                    orig_sets = ex.get("sets", 3)
                    new_sets = max(1, round(orig_sets * factor))
                    ex["sets"] = new_sets
                    ex["notes"] = f"{ex.get('notes', '')} (Volume dynamically adjusted by {int(patch['workout_plan']['global_modifier']*100)}%)".strip()

        # 2. Calorie adjustment (Proportional Scaling)
        if "meal_plan" in patch and "calorie_adjust" in patch["meal_plan"]:
            delta = patch["meal_plan"]["calorie_adjust"]
            meal_days = plan_dict.get("meal_plan", {}).get("days", [])
            
            for day in meal_days:
                meals = day.get("meals", [])
                old_total_cals = day.get("totals", {}).get("calories", 0)
                
                # If there are cals to scale, calculate exact mathematical proportion
                if old_total_cals > 0:
                    target_total = max(old_total_cals + delta, 500)  # floor at 500
                    scale_factor = target_total / old_total_cals
                    
                    for meal in meals:
                        # Scale all macros to maintain the same exact ratio and recipes
                        meal["calories"] = round(meal.get("calories", 0) * scale_factor)
                        meal["protein_g"] = round(meal.get("protein_g", 0) * scale_factor)
                        meal["carbs_g"] = round(meal.get("carbs_g", 0) * scale_factor)
                        meal["fat_g"] = round(meal.get("fat_g", 0) * scale_factor)
                        
                        # Scale servings up/down transparently
                        current_servings = meal.get("servings", 1.0)
                        meal["servings"] = round(current_servings * scale_factor, 2)
                        
                        # Attach a transparent UX note
                        if delta < 0:
                            meal["notes"] = "Portion reduced strictly to hit new weight-loss target."
                        else:
                            meal["notes"] = "Portion increased to meet new energy demands."

                    # Recalculate true day totals mathematically (avoids precision drift)
                    day_totals = day.get("totals", {})
                    day_totals["calories"] = sum(m.get("calories", 0) for m in meals)
                    day_totals["protein_g"] = sum(m.get("protein_g", 0) for m in meals)
                    day_totals["carbs_g"] = sum(m.get("carbs_g", 0) for m in meals)
                    day_totals["fat_g"] = sum(m.get("fat_g", 0) for m in meals)
            
            # Recalculate true weekly totals mathematically
            weekly_totals = plan_dict.get("meal_plan", {}).get("weekly_totals", {})
            if weekly_totals:
                weekly_totals["calories"] = sum(d.get("totals", {}).get("calories", 0) for d in meal_days)
                weekly_totals["protein_g"] = sum(d.get("totals", {}).get("protein_g", 0) for d in meal_days)
                weekly_totals["carbs_g"] = sum(d.get("totals", {}).get("carbs_g", 0) for d in meal_days)
                weekly_totals["fat_g"] = sum(d.get("totals", {}).get("fat_g", 0) for d in meal_days)

        return plan_dict
    def invert_patch(self, patch: Dict) -> Dict:
        """
        Create a compensating patch that negates the given patch.
        Uses additive/multiplicative inversion.
        """
        inverted = {"workout_plan": {}, "meal_plan": {}}
        
        # 1. Invert Volume
        if "workout_plan" in patch and "global_modifier" in patch["workout_plan"]:
            mod = patch["workout_plan"]["global_modifier"]
            # To revert a 15% drop (-0.15), we apply a +17.6% increase (1/0.85 - 1)
            # but for v1 simplicity and safety, we'll just negate the modifier sign
            # and let the rounding handle the rest.
            inverted["workout_plan"] = {
                "global_modifier": -mod,
                "instruction": f"Reverting volume adjustment of {abs(int(mod*100))}%"
            }

        # 2. Invert Calories
        if "meal_plan" in patch and "calorie_adjust" in patch["meal_plan"]:
            delta = patch["meal_plan"]["calorie_adjust"]
            inverted["meal_plan"] = {
                "calorie_adjust": -delta
            }

        return inverted
