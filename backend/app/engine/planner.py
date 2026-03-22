"""
AI Fitness Coach v1 — LLM Planner

The planning engine that generates personalized workout and meal plans
using an LLM for reasoning, with structured JSON outputs.
"""
from typing import Optional, List
from datetime import datetime, timedelta
import json
import logging
from app.config import settings
from app.logging_config import get_logger, track_timing
from app.engine.models import (
    NormalizedWorkoutDay, 
    NormalizedMealDay, 
    NormalizedMacros,
    NormalizedExercise,
    NormalizedMeal
)

logger = get_logger("planner")

# ─── Prompt Templates ──────────────────────────────────────────

COMMON_INSTRUCTIONS = """
Respond with ONLY valid JSON. 
Do not include any conversational text outside the JSON.
If you use markdown blocks, ensure they are correctly closed.
"""

WORKOUT_PLAN_PROMPT = """You are an expert fitness coach creating a personalized weekly workout plan.

## User Profile
- Goal: {goal}
- Available equipment: {equipment}
- Training days per week: {days_per_week}
- Session length: {session_length_min} minutes
- Preferred time: {preferred_workout_time}
- Injuries: {injuries}

## Recent Performance
{recent_performance}

## Instructions
Create a {days_per_week}-day workout plan for the week starting {week_start}.
Consider {equipment} constraints.
{instructions}

Return JSON format:
{{
  "split_type": "string",
  "notes": "string",
  "days": [
    {{
      "day": "string",
      "day_number": int,
      "focus": "string",
      "is_rest_day": bool,
      "estimated_duration_min": int,
      "warmup_notes": "string",
      "exercises": [
        {{
          "name": "string",
          "muscle_group": "string",
          "sets": int,
          "reps": "string",
          "weight_kg": float,
          "rest_sec": int,
          "notes": "string",
          "substitutions": ["string"]
        }}
      ]
    }}
  ]
}}

### SINGLE DAY WORKOUT PROMPT
To generate just ONE day of a workout:
Return JSON:
{{
  "day": "string",
  "day_number": int,
  "focus": "string",
  "is_rest_day": bool,
  "estimated_duration_min": int,
  "warmup_notes": "string",
  "exercises": [ ... same as above ... ]
}}
""" + COMMON_INSTRUCTIONS

MEAL_PLAN_PROMPT = """You are an expert nutritionist creating a personalized weekly meal plan.

## Targets
- Calories: {target_calories} | Protein: {target_protein_g}g

## Preferences
- Restrictions: {dietary_restrictions}
- Preferences: {dietary_preferences}

## Available Recipes
{available_recipes}

## Instructions
Create a {days_to_plan}-day meal plan.
{instructions}

Return JSON format:
{{
  "notes": "string",
  "days": [
    {{
      "day": "string",
      "day_number": int,
      "meals": [
        {{
          "meal_type": "breakfast|lunch|dinner|snack",
          "name": "string",
          "servings": float,
          "calories": int,
          "protein_g": int,
          "carbs_g": int,
          "fat_g": int,
          "recipe_id": "string|null"
        }}
      ],
      "totals": {{
        "calories": int, "protein_g": int, "carbs_g": int, "fat_g": int
      }}
    }}
  ]
}}

### SINGLE DAY MEAL PROMPT
To generate just ONE day of meals:
Return JSON:
{{
  "day": "string",
  "day_number": int,
  "meals": [ ... same as above ... ],
  "totals": {{ ... }}
}}
""" + COMMON_INSTRUCTIONS


class LLMPlanner:
    """
    LLM-based planning engine for generating workout and meal plans.
    """

    def __init__(self):
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url
        self.max_response_size = 8000 # 8KB safety limit

    def _get_model_string(self) -> str:
        if self.provider == "ollama": return f"ollama/{self.model}"
        return self.model

    @track_timing("planner", "llm_call")
    async def _call_llm(self, prompt: str, system_message: str = "") -> str:
        import litellm
        
        # Log input (truncated)
        logger.info("llm_request_start", prompt_len=len(prompt))
        
        try:
            response = await litellm.acompletion(
                model=self._get_model_string(),
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, # Lower for more consistent JSON
                max_tokens=2000,
                api_base=self.base_url if self.provider == "ollama" else None,
                timeout=300,
            )
            
            content = response.choices[0].message.content
            
            # 1. Strip <think> tags
            if "<think>" in content:
                content = content.split("</think>")[-1].strip()
                
            # 2. Safety Check: Response size
            if len(content) > self.max_response_size:
                logger.error("llm_response_oversize", size=len(content))
                raise ValueError("LLM response exceeded safety size limit")

            logger.info("llm_request_success", response_len=len(content))
            return content

        except Exception as e:
            logger.error("llm_request_failed", error=str(e))
            raise

    def _parse_json(self, text: str) -> dict:
        """Robust JSON parsing with multiple strategies."""
        try:
            # 1. Direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            # 2. Markdown block extraction
            for block in ["```json", "```"]:
                if block in text:
                    try:
                        start = text.index(block) + len(block)
                        end = text.index("```", start)
                        return json.loads(text[start:end].strip())
                    except: pass
            
            # 3. Last resort: Boundary finding
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(text[start:end])
            except: pass
            
        logger.error("json_parse_failed", text_preview=text[:200])
        raise ValueError("Could not extract valid JSON from LLM response")

    async def generate_workout_plan(
        self,
        profile: dict,
        recent_performance: str = "None",
        fast_mode: bool = False
    ) -> List[NormalizedWorkoutDay]:
        """Generate normalized workout days by calling LLM for each day."""
        days_count = 3 if fast_mode else 7 # Plan for full week but only days_per_week are active
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if fast_mode: day_names = day_names[:3]

        workout_days = []
        for i, day_name in enumerate(day_names):
            logger.info("generating_workout_day", day=day_name, index=i+1)
            
            # Determine if this should be a rest day based on profile.days_per_week
            # Simple heuristic: if we want 4 days, mark Wed/Sat/Sun as rest if i is and etc.
            # But let's let the LLM decide the focus/rest for each specific day name.
            
            prompt = WORKOUT_PLAN_PROMPT.format(
                goal=profile.get("goal", "muscle_gain"),
                equipment=", ".join(profile.get("equipment", ["bodyweight"])),
                days_per_week=profile.get("days_per_week", 4),
                session_length_min=profile.get("session_length_min", 45),
                preferred_workout_time=profile.get("preferred_workout_time", "evening"),
                injuries=", ".join(profile.get("injuries", [])),
                recent_performance=recent_performance,
                week_start=datetime.now().strftime("%Y-%m-%d"),
                instructions=f"Generate ONLY the plan for {day_name} (Day {i+1} of the week)."
            )

            raw = await self._call_llm(prompt, "You are a world-class CSCS fitness coach. Generate JSON for ONE day.")
            data = self._parse_json(raw)
            
            # If the LLM returned a 'days' list, take the first one. Otherwise assume it returned the day directly.
            day_data = data.get("days", [data])[0]
            workout_days.append(NormalizedWorkoutDay(**day_data))
            
        return workout_days

    async def generate_meal_plan(
        self,
        profile: dict,
        available_recipes: str = "None",
        fast_mode: bool = False
    ) -> List[NormalizedMealDay]:
        """Generate normalized meal days by calling LLM for each day."""
        days_to_plan = 2 if fast_mode else 7
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if fast_mode: day_names = day_names[:2]

        meal_plan_days = []
        for i, day_name in enumerate(day_names):
            logger.info("generating_meal_day", day=day_name, index=i+1)
            
            prompt = MEAL_PLAN_PROMPT.format(
                target_calories=profile.get("target_calories", 2000),
                target_protein_g=profile.get("target_protein_g", 150),
                dietary_restrictions=", ".join(profile.get("dietary_restrictions", [])),
                dietary_preferences=", ".join(profile.get("dietary_preferences", [])),
                available_recipes=available_recipes,
                days_to_plan=1,
                instructions=f"Generate ONLY the meal plan for {day_name} (Day {i+1} of the sequence)."
            )

            raw = await self._call_llm(prompt, "You are a clinical sports nutritionist. Generate JSON for ONE day.")
            data = self._parse_json(raw)
            
            # Take the first day from 'days' or assume the root is the day object
            day_data = data.get("days", [data])[0]
            
            # Normalize nested meals
            meals = []
            for m in day_data.get("meals", []):
                macros = NormalizedMacros(
                    calories=m.get("calories", 0),
                    protein_g=m.get("protein_g", 0),
                    carbs_g=m.get("carbs_g", 0),
                    fat_g=m.get("fat_g", 0)
                )
                meals.append(NormalizedMeal(
                    meal_type=m.get("meal_type", "snack"),
                    name=m.get("name", "Unnamed Meal"),
                    servings=m.get("servings", 1.0),
                    macros=macros,
                    recipe_id=m.get("recipe_id"),
                    notes=m.get("notes", "")
                ))
            
            day_data["meals"] = meals
            day_data["daily_totals"] = NormalizedMacros(**day_data.get("totals", day_data.get("daily_totals", {})))
            meal_plan_days.append(NormalizedMealDay(**day_data))
            
        return meal_plan_days

    def _mock_response(self, prompt: str) -> str:
        """Minimal fallback for total LLM failure."""
        return json.dumps({
            "split_type": "Full Body",
            "notes": "Fallback plan due to system error",
            "days": []
        })

if __name__ == "__main__":
    import asyncio
    async def test():
        planner = LLMPlanner()
        profile = {"goal": "muscle_gain", "equipment": ["dumbbells"], "days_per_week": 3, "user_id": "test"}
        plan = await planner.generate_workout_plan(profile, fast_mode=True)
        print(f"Generated {len(plan)} days")
        for d in plan:
            print(f"Day: {d.day}, focus: {d.focus}, exercises: {len(d.exercises)}")
    
    asyncio.run(test())
