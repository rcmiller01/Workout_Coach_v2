"""
AI Fitness Coach v1 — Substitution Engine

Provides exercise and recipe substitutions based on:
- Equipment constraints
- Injury workarounds
- User preferences
- Goal optimization
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SubstitutionEngine:
    """
    Provides intelligent substitutions for exercises and recipes
    based on user constraints and preferences.
    """

    # ─── Exercise Substitution Maps ────────────────────────────
    #
    # Structure: {exercise: {constraint: [alternatives]}}
    # Constraints: "no_barbell", "no_rack", "bodyweight", "joint_friendly"

    EXERCISE_SUBSTITUTIONS = {
        # ── Chest ──
        "bench press": {
            "no_barbell": ["Dumbbell Press", "Machine Chest Press"],
            "no_rack": ["Dumbbell Press", "Floor Press", "Push-ups"],
            "bodyweight": ["Push-ups", "Diamond Push-ups", "Dip"],
            "joint_friendly": ["Cable Fly", "Machine Chest Press", "Push-ups"],
        },
        "incline bench press": {
            "no_barbell": ["Incline Dumbbell Press", "Incline Machine Press"],
            "bodyweight": ["Decline Push-ups", "Pike Push-ups"],
            "joint_friendly": ["Incline Dumbbell Fly", "Low Cable Fly"],
        },
        # ── Back ──
        "barbell row": {
            "no_barbell": ["Dumbbell Row", "Cable Row"],
            "bodyweight": ["Inverted Row", "Band Row"],
            "joint_friendly": ["Cable Row", "Machine Row", "Chest-Supported DB Row"],
        },
        "deadlift": {
            "no_barbell": ["Dumbbell Deadlift", "Trap Bar Deadlift"],
            "bodyweight": ["Glute Bridge", "Single Leg Deadlift (BW)"],
            "joint_friendly": ["Trap Bar Deadlift", "Hip Hinge Machine", "Cable Pull-Through"],
        },
        "pull-up": {
            "no_rack": ["Lat Pulldown", "Band Pulldown"],
            "bodyweight": ["Door Frame Pull-ups", "Inverted Row"],
            "joint_friendly": ["Lat Pulldown", "Cable Pullover"],
        },
        "lat pulldown": {
            "bodyweight": ["Pull-ups", "Band Pulldown"],
            "no_cables": ["Dumbbell Pullover", "Band Pulldown"],
        },
        # ── Legs ──
        "squat": {
            "no_barbell": ["Goblet Squat", "Dumbbell Squat", "Leg Press"],
            "no_rack": ["Goblet Squat", "Bulgarian Split Squat", "Leg Press"],
            "bodyweight": ["Bodyweight Squat", "Pistol Squat", "Jump Squat"],
            "joint_friendly": ["Leg Press", "Goblet Squat", "Box Squat"],
        },
        "leg press": {
            "bodyweight": ["Squat", "Lunge", "Step-up"],
            "no_machine": ["Goblet Squat", "Bulgarian Split Squat"],
        },
        "romanian deadlift": {
            "no_barbell": ["Dumbbell RDL", "Single Leg DB RDL"],
            "bodyweight": ["Single Leg Deadlift", "Nordic Curl", "Glute Bridge"],
            "joint_friendly": ["Seated Leg Curl", "Stability Ball Curl"],
        },
        "lunge": {
            "joint_friendly": ["Step-up", "Leg Press", "Split Squat (shallow)"],
            "bodyweight": ["Walking Lunge", "Reverse Lunge", "Step-up"],
        },
        # ── Shoulders ──
        "overhead press": {
            "no_barbell": ["Dumbbell Shoulder Press", "Arnold Press"],
            "bodyweight": ["Pike Push-ups", "Handstand Push-ups"],
            "joint_friendly": ["Lateral Raise", "Cable Lateral Raise", "Machine Press"],
        },
        "lateral raise": {
            "bodyweight": ["Band Lateral Raise", "Wall Slide"],
            "joint_friendly": ["Cable Lateral Raise", "Light DB Lateral Raise"],
        },
        # ── Arms ──
        "barbell curl": {
            "no_barbell": ["Dumbbell Curl", "Hammer Curl"],
            "bodyweight": ["Chin-ups", "Band Curl"],
            "joint_friendly": ["Cable Curl", "Hammer Curl"],
        },
        "skull crusher": {
            "joint_friendly": ["Cable Pushdown", "Overhead Cable Extension"],
            "bodyweight": ["Diamond Push-ups", "Bench Dip"],
        },
    }

    # ─── Recipe Substitution Strategies ────────────────────────

    RECIPE_SWAP_STRATEGIES = {
        "high_protein": {
            "description": "Higher protein alternative",
            "swap_rules": {
                "pasta": "protein pasta or zoodles with chicken",
                "rice": "cauliflower rice with extra protein",
                "bread": "protein wrap or lettuce wrap",
                "cereal": "protein oats or Greek yogurt bowl",
            }
        },
        "quick_meal": {
            "description": "Faster preparation time",
            "swap_rules": {
                "slow_cook": "sheet pan or stir fry version",
                "complex": "simplified one-pot version",
            }
        },
        "lower_calorie": {
            "description": "Reduced calorie alternative",
            "swap_rules": {
                "fried": "baked or air-fried version",
                "creamy_sauce": "tomato-based or broth-based sauce",
                "heavy_carb": "veggie-based substitute",
            }
        },
    }

    def get_exercise_substitutions(
        self,
        exercise_name: str,
        constraint: str = "no_barbell",
        user_equipment: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Get exercise substitutions based on a constraint.

        Args:
            exercise_name: Name of the exercise to substitute
            constraint: The reason for substitution
            user_equipment: Available equipment to filter results

        Returns:
            List of alternative exercise names
        """
        name_lower = exercise_name.lower()
        exercise_subs = self.EXERCISE_SUBSTITUTIONS.get(name_lower, {})
        alternatives = exercise_subs.get(constraint, [])

        if not alternatives:
            # Try partial matching
            for ex_name, subs in self.EXERCISE_SUBSTITUTIONS.items():
                if ex_name in name_lower or name_lower in ex_name:
                    alternatives = subs.get(constraint, [])
                    if alternatives:
                        break

        # Filter by available equipment if specified
        if user_equipment and alternatives:
            equipment_set = set(e.lower() for e in user_equipment)
            # Simple filter: keep exercises that don't require unavailable equipment
            # (This is a heuristic — a more robust solution would use an exercise DB)
            filtered = []
            for alt in alternatives:
                alt_lower = alt.lower()
                needs_cable = "cable" in alt_lower
                needs_machine = "machine" in alt_lower
                needs_barbell = "barbell" in alt_lower

                if needs_cable and "cables" not in equipment_set:
                    continue
                if needs_barbell and "barbell" not in equipment_set:
                    continue
                # Machines are generally available at gyms
                filtered.append(alt)

            return filtered if filtered else alternatives

        return alternatives

    def suggest_constraint_from_profile(self, profile: dict) -> list[str]:
        """
        Determine applicable constraints from the user profile.

        Returns list of constraint types to apply.
        """
        constraints = []
        equipment = set(e.lower() for e in profile.get("equipment", []))

        if "barbell" not in equipment:
            constraints.append("no_barbell")
        if "rack" not in equipment:
            constraints.append("no_rack")
        if not equipment or equipment == {"bodyweight"}:
            constraints.append("bodyweight")

        injuries = profile.get("injuries", [])
        if injuries:
            constraints.append("joint_friendly")

        return constraints

    def auto_substitute_workout(self, workout_plan: dict, profile: dict) -> dict:
        """
        Automatically apply substitutions to a workout plan based on
        the user's equipment and injury constraints.
        """
        constraints = self.suggest_constraint_from_profile(profile)
        equipment = profile.get("equipment", [])
        modified = False

        for day in workout_plan.get("days", []):
            for exercise in day.get("exercises", []):
                for constraint in constraints:
                    subs = self.get_exercise_substitutions(
                        exercise["name"],
                        constraint=constraint,
                        user_equipment=equipment,
                    )
                    if subs:
                        # Store original and add substitutions
                        if not exercise.get("substitutions"):
                            exercise["substitutions"] = subs
                        # If this is an equipment constraint violation, auto-swap
                        if constraint in ("no_barbell", "no_rack", "bodyweight"):
                            original = exercise["name"]
                            exercise["name"] = subs[0]
                            exercise["substitutions"] = [original] + subs[1:]
                            modified = True
                            logger.info(
                                f"Auto-substituted '{original}' → '{subs[0]}' ({constraint})"
                            )
                            break

        return workout_plan
