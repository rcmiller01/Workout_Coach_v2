"""
AI Fitness Coach v1 — Planning Service

Higher-level orchestration logic for the weekly planning workflow.
Handles locking, versioning, and rule validation.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Set

from app.engine.planner import LLMPlanner
from app.engine.rules import RulesEngine
from app.engine.substitution import SubstitutionEngine
from app.engine.sync import SyncEngine
from app.engine.models import NormalizedPlan, NormalizedWorkoutDay, NormalizedMealDay
from app.providers.wger import WgerProvider
from app.providers.tandoor import TandoorProvider
from app.logging_config import get_logger, track_timing

logger = get_logger("planning_service")

# In-memory lock for plan generation (prevents duplicate calls)
ACTIVE_GENERATIONS: Set[str] = set()


from app.engine.replanner import Replanner

class PlanningService:
    """
    Orchestrates the complete weekly planning workflow.
    """

    def __init__(
        self,
        wger: WgerProvider,
        tandoor: TandoorProvider,
    ):
        self.wger = wger
        self.tandoor = tandoor
        self.planner = LLMPlanner()
        self.replanner = Replanner()
        self.rules = RulesEngine()
        self.substitution = SubstitutionEngine()
        self.sync = SyncEngine(wger, tandoor)

    @track_timing("planning_service", "replan")
    async def replan_active_plan(
        self,
        user_id: str,
        current_plan_dict: dict,
        adherence_summary: dict,
        weight_delta_kg: float,
        goal: str,
        last_revision_dates: dict = None,
        sensitivity_settings: dict = None
    ) -> tuple[str, str, dict, dict, bool]:
        """
        Produce a delta patch for the current plan based on adherence/weight.

        Args:
            sensitivity_settings: Optional per-user overrides for thresholds:
                - weight_threshold_kg: Weight trend threshold before calorie changes
                - missed_workout_threshold: Missed workouts before volume reductions
                - cooldown_days: Cooldown window between revisions in same area

        Returns: (trigger, reason, patch, updated_plan_dict, is_auto_applied)
        """
        # 1. Calculate Patch
        trigger, reason, patch = self.replanner.calculate_adjustment(
            current_plan_dict,
            adherence_summary,
            weight_delta_kg,
            goal,
            last_revision_dates,
            sensitivity_settings
        )

        # 2. Determine if auto-applied (small changes only)
        # Threshold: Calorie shift <= 100 AND volume shift <= 10%
        cal_adjust = patch.get("meal_plan", {}).get("calorie_adjust", 0)
        vol_adjust = patch.get("workout_plan", {}).get("global_modifier", 0.0)
        
        is_auto_applied = abs(cal_adjust) <= 100 and abs(vol_adjust) <= 0.10

        # 3. Apply Patch to produce updated plan
        updated_plan = self.replanner.apply_patch_to_plan(
            current_plan_dict.copy(), # Work on a copy
            patch
        )

        return trigger, reason, patch, updated_plan, is_auto_applied


    def _format_recent_performance(self, workout_data: Optional[dict]) -> str:
        """Format recent workout data for LLM context."""
        if not workout_data:
            return "No recent workout data available."

        results = workout_data.get("results", [])
        if not results:
            return "No recent workout logs found."

        summary = f"Summary: {len(results)} recent logs found. User is consistent."
        return summary

    def _format_available_recipes(self, recipes: Optional[list]) -> str:
        """Format available recipes for LLM context."""
        if not recipes:
            return "No recipes available. Propose new ones."

        names = [r.get("name", "Unknown") for r in recipes[:10]]
        return f"Existing recipes to favor: {', '.join(names)}"


    async def undo_replan(
        self,
        user_id: str,
        target_revision_patch: dict,
        current_plan_dict: dict
    ) -> tuple[str, str, dict, dict]:
        """
        Reverse a specific auto-applied revision by creating a compensating patch.
        Returns: (trigger, reason, patch, updated_plan_dict)
        """
        # 1. Invert the patch
        reversal_patch = self.replanner.invert_patch(target_revision_patch)
        
        trigger = "user_undo"
        reason = "User reverted auto-adjustment."
        
        # 2. Apply compensating patch
        updated_plan = self.replanner.apply_patch_to_plan(
            current_plan_dict.copy(),
            reversal_patch
        )
        
        return trigger, reason, reversal_patch, updated_plan

    @track_timing("planning_service", "create_plan")

    async def create_weekly_plan(
        self,
        profile: dict,
        fast_mode: bool = False,
        is_replan: bool = False,
        max_retries: int = 1,
    ) -> NormalizedPlan:
        """
        Full planning workflow with retry on validation failure.
        """
        user_id = profile["user_id"]
        
        # 1. Generation Lock
        if user_id in ACTIVE_GENERATIONS:
            logger.warning("duplicate_generation_attempt", user_id=user_id)
            raise ValueError("Plan generation already in progress for this user")
            
        ACTIVE_GENERATIONS.add(user_id)
        
        try:
            # 2. Gather context
            provider_data = await self.sync.gather_planning_data(profile)
            recent_perf = self._format_recent_performance(provider_data.get("recent_workouts"))
            available_recipes = self._format_available_recipes(provider_data.get("available_recipes"))

            best_plan = None
            
            for attempt in range(max_retries + 1):
                logger.info("generation_attempt", user_id=user_id, attempt=attempt+1)
                
                try:
                    # 3. Generate Workout Plan
                    workout_days: List[NormalizedWorkoutDay] = await self.planner.generate_workout_plan(
                        profile=profile,
                        recent_performance=recent_perf,
                        fast_mode=fast_mode
                    )

                    # 4. Generate Meal Plan
                    meal_days: List[NormalizedMealDay] = await self.planner.generate_meal_plan(
                        profile=profile,
                        available_recipes=available_recipes,
                        fast_mode=fast_mode
                    )

                    # 5. Build full plan object
                    plan = NormalizedPlan(
                        plan_id=str(uuid.uuid4()),
                        user_id=user_id,
                        week_start=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        week_end=(datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d"),
                        workout_plan=workout_days,
                        meal_plan=meal_days,
                        is_replan=is_replan,
                        metadata={"fast_mode": fast_mode, "attempt": attempt + 1}
                    )

                    # 6. Validate & Self-Correct
                    # Convert Pydantic models back to dict for the current rules engine (to be updated later)
                    plan_dict = plan.dict()
                    # Rules engine expects {"days": [...]} wrapper, but plan.dict() returns raw lists
                    workout_for_rules = plan_dict["workout_plan"] if isinstance(plan_dict["workout_plan"], dict) else {"days": plan_dict["workout_plan"]}
                    meal_for_rules = plan_dict["meal_plan"] if isinstance(plan_dict["meal_plan"], dict) else {"days": plan_dict["meal_plan"]}
                    validation = self.rules.validate_plan(
                        workout_for_rules,
                        meal_for_rules,
                        profile
                    )
                    
                    plan.rules_applied = (
                        validation.get("workout", {}).get("rules_applied", []) +
                        validation.get("meal", {}).get("rules_applied", [])
                    )

                    if validation.get("is_valid", False):
                        logger.info("plan_validated", user_id=user_id)
                        return plan

                    # Store as "best attempt" if valid enough
                    workout_errors = validation.get("workout", {}).get("errors", [])
                    meal_errors = validation.get("meal", {}).get("errors", [])
                    logger.warning("validation_failed", user_id=user_id, errors=workout_errors + meal_errors)
                    best_plan = plan

                except Exception as e:
                    import traceback
                    logger.error("generation_error", user_id=user_id, error=str(e), traceback=traceback.format_exc())
                    if attempt == max_retries: raise

            return best_plan

        finally:
            ACTIVE_GENERATIONS.remove(user_id)

    def _format_recent_performance(self, workout_data: Optional[dict]) -> str:
        """Format recent workout data for LLM context."""
        if not workout_data:
            return "No recent workout data available."

        results = workout_data.get("results", [])
        if not results:
            return "No recent workout logs found."

        summary = f"Summary: {len(results)} recent logs found. User is consistent."
        return summary

    def _format_available_recipes(self, recipes: Optional[list]) -> str:
        """Format available recipes for LLM context."""
        if not recipes:
            return "No recipes available. Propose new ones."

        names = [r.get("name", "Unknown") for r in recipes[:10]]
        return f"Existing recipes to favor: {', '.join(names)}"

