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

WORKOUT_PLAN_PROMPT = """Generate a workout for {day_name} (Day {day_number}).

Profile: Goal={goal}, Equipment={equipment}, Session={session_length_min}min, Injuries={injuries}
Preferences: {workout_notes}
Week schedule: {week_schedule}
Already used exercises this week: {previous_days_summary}

{day_assignment}

Rules: ONLY use {equipment}. Aim for {session_length_min} minutes. Use DIFFERENT exercises from those already listed above.

Return JSON:
{{"day":"{day_name}","day_number":{day_number},"focus":"string","is_rest_day":false,"estimated_duration_min":int,"warmup_notes":"string","exercises":[{{"name":"string","muscle_group":"string","sets":int,"reps":"string","weight_kg":float,"rest_sec":int,"notes":"string","substitutions":["string"]}}]}}
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
    async def _call_llm(self, prompt: str, system_message: str = "", num_predict: int = 4096) -> str:
        """
        Call the LLM. Uses direct httpx for Ollama (avoids litellm stripping
        thinking-model content), falls back to litellm for other providers.
        """
        logger.info("llm_request_start", prompt_len=len(prompt))

        try:
            if self.provider == "ollama":
                content = await self._call_ollama_direct(prompt, system_message, num_predict=num_predict)
            else:
                content = await self._call_litellm(prompt, system_message)

            # 1. Strip <think> tags (thinking models like qwen3)
            if "<think>" in content:
                content = content.split("</think>")[-1].strip()

            # 2. Safety Check: Response size
            if len(content) > self.max_response_size:
                logger.error("llm_response_oversize", size=len(content))
                raise ValueError("LLM response exceeded safety size limit")

            if not content:
                raise ValueError("LLM returned empty response after processing")

            logger.info("llm_request_success", response_len=len(content))
            return content

        except Exception as e:
            logger.error("llm_request_failed", error=str(e))
            raise

    async def _call_ollama_direct(self, prompt: str, system_message: str = "", num_predict: int = 4096) -> str:
        """Direct Ollama API call via httpx — avoids litellm compatibility issues."""
        import httpx

        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_message or "You are a helpful assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": num_predict,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

    async def _call_litellm(self, prompt: str, system_message: str = "") -> str:
        """LiteLLM call for non-Ollama providers (OpenAI, Anthropic, etc.)."""
        import litellm

        response = await litellm.acompletion(
            model=self._get_model_string(),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=4096,
            api_base=self.base_url if self.provider == "ollama" else None,
            timeout=300,
        )
        return response.choices[0].message.content or ""

    def _parse_json(self, text: str) -> dict:
        """Robust JSON parsing with multiple strategies."""
        def _unwrap(obj):
            """If the LLM returned a list with one element, unwrap it to a dict."""
            if isinstance(obj, list) and len(obj) >= 1:
                return obj[0]
            return obj

        try:
            # 1. Direct parse
            return _unwrap(json.loads(text))
        except json.JSONDecodeError:
            # 2. Markdown block extraction
            for block in ["```json", "```"]:
                if block in text:
                    try:
                        start = text.index(block) + len(block)
                        end = text.index("```", start)
                        return _unwrap(json.loads(text[start:end].strip()))
                    except: pass

            # 3. Last resort: Boundary finding
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    return _unwrap(json.loads(text[start:end]))
            except: pass

        logger.error("json_parse_failed", text_preview=text[:200])
        raise ValueError("Could not extract valid JSON from LLM response")

    def _build_week_schedule(self, days_per_week: int, goal: str) -> list[dict]:
        """
        Pre-compute which days are training vs rest, and assign focus areas.
        Returns a list of 7 dicts: [{day, is_rest, focus_hint}, ...]
        """
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        # Common split patterns by training days
        SPLITS = {
            2: {
                "schedule": [True, False, False, True, False, False, False],
                "focuses": ["Full Body A", "Full Body B"],
            },
            3: {
                "schedule": [True, False, True, False, True, False, False],
                "focuses": ["Push + Core", "Pull + Legs", "Full Body Conditioning"],
            },
            4: {
                "schedule": [True, True, False, True, True, False, False],
                "focuses": ["Upper Body Strength", "Lower Body Strength", None, "Upper Body Hypertrophy", "Lower Body & Conditioning"],
            },
            5: {
                "schedule": [True, True, True, False, True, True, False],
                "focuses": ["Push", "Pull", "Legs", None, "Upper Body", "Lower Body & Conditioning"],
            },
            6: {
                "schedule": [True, True, True, True, True, True, False],
                "focuses": ["Push", "Pull", "Legs", "Push Variation", "Pull Variation", "Legs & Conditioning"],
            },
            7: {
                "schedule": [True, True, True, True, True, True, True],
                "focuses": ["Push", "Pull", "Legs", "Upper Strength", "Lower Strength", "Conditioning", "Active Recovery"],
            },
        }

        split = SPLITS.get(days_per_week, SPLITS[4])
        schedule = split["schedule"]
        focuses = split["focuses"]

        result = []
        focus_idx = 0
        for i, day_name in enumerate(day_names):
            is_training = schedule[i] if i < len(schedule) else False
            if is_training and focus_idx < len(focuses):
                focus = focuses[focus_idx]
                focus_idx += 1
                if focus is None:  # Skip None entries (rest days within the focuses list)
                    result.append({"day": day_name, "is_rest": True, "focus_hint": "Rest & Recovery"})
                    continue
                result.append({"day": day_name, "is_rest": False, "focus_hint": focus})
            else:
                result.append({"day": day_name, "is_rest": True, "focus_hint": "Rest & Recovery"})

        return result

    async def generate_workout_plan(
        self,
        profile: dict,
        recent_performance: str = "None",
        fast_mode: bool = False
    ) -> List[NormalizedWorkoutDay]:
        """Generate normalized workout days by calling LLM for each day."""
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        days_per_week = profile.get("days_per_week", 4)
        session_length = profile.get("session_length_min", 45)
        equipment = ", ".join(profile.get("equipment", ["bodyweight"]))

        # 1. Pre-compute the weekly schedule
        week_schedule = self._build_week_schedule(days_per_week, profile.get("goal", "maintenance"))

        if fast_mode:
            # In fast mode, only generate first 3 days
            week_schedule = week_schedule[:3]
            day_names = day_names[:3]

        # Format the schedule for the prompt
        def _fmt_sched(s):
            if s["is_rest"]:
                return f"- {s['day']}: REST DAY"
            return f"- {s['day']}: TRAINING — {s['focus_hint']}"
        schedule_str = "\n".join([_fmt_sched(s) for s in week_schedule])

        workout_days = []
        for i, sched in enumerate(week_schedule):
            day_name = sched["day"]
            is_rest = sched["is_rest"]
            focus_hint = sched["focus_hint"]

            logger.info("generating_workout_day", day=day_name, index=i+1, is_rest=is_rest)

            # For rest days, skip the LLM call entirely
            if is_rest:
                workout_days.append(NormalizedWorkoutDay(
                    day=day_name,
                    day_number=i + 1,
                    focus="Rest & Recovery",
                    is_rest_day=True,
                    estimated_duration_min=0,
                    warmup_notes="Light stretching or walking recommended.",
                    exercises=[],
                ))
                continue

            # Build summary of previously generated training days for variety
            prev_summary = "None yet — this is the first training day."
            if workout_days:
                prev_lines = []
                for prev in workout_days:
                    if not prev.is_rest_day and prev.exercises:
                        ex_names = [e.name for e in prev.exercises]
                        prev_lines.append(f"  {prev.day} ({prev.focus}): {', '.join(ex_names)}")
                if prev_lines:
                    prev_summary = "\n".join(prev_lines)

            # Build the day assignment instruction
            day_assignment = f"This is a TRAINING DAY. Focus area: **{focus_hint}**. Generate {5}-{7} exercises targeting this focus."

            prompt = WORKOUT_PLAN_PROMPT.format(
                goal=profile.get("goal", "muscle_gain"),
                equipment=equipment,
                session_length_min=session_length,
                injuries=", ".join(profile.get("injuries", [])) or "None",
                workout_notes=profile.get("workout_notes", "No special preferences."),
                week_schedule=schedule_str,
                previous_days_summary=prev_summary,
                day_name=day_name,
                day_number=i + 1,
                day_assignment=day_assignment,
            )

            raw = await self._call_llm(prompt, "You are a world-class CSCS fitness coach. Generate JSON for ONE day. Ensure exercise variety across the week.")
            data = self._parse_json(raw)

            # If the LLM returned a list, unwrap it first
            if isinstance(data, list):
                data = data[0]
            # If the LLM returned a 'days' list, take the first one
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
            
            # If the LLM returned a list, unwrap it first
            if isinstance(data, list):
                data = data[0]
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
