"""
AI Fitness Coach v1 — wger Workout Provider

Adapter for the wger Workout Manager REST API (v2).
Handles: exercises, routines, workout logs, body weight, nutrition diary.

wger API docs: https://wger.readthedocs.io/en/latest/api/index.html
"""
from typing import Optional
from app.providers.base import BaseProvider, ProviderError
from datetime import date, datetime


class WgerProvider(BaseProvider):
    """
    Provider adapter for wger — the system of record for workouts,
    body metrics, and exercise data.
    """

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.api_token}"}

    async def health_check(self) -> bool:
        """Check if wger is reachable by hitting the exercise list endpoint."""
        try:
            result = await self.get("/exercise/", params={"format": "json", "limit": 1})
            return "results" in result or "count" in result
        except Exception:
            return False

    # ─── Exercises ─────────────────────────────────────────────

    async def list_exercises(
        self,
        language: int = 2,  # English
        category: Optional[int] = None,
        muscles: Optional[list[int]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        List exercises from wger.
        Categories: 8=Arms, 9=Legs, 10=Abs, 11=Chest, 12=Back, 13=Shoulders, 14=Calves
        """
        params = {
            "format": "json",
            "language": language,
            "limit": limit,
            "offset": offset,
        }
        if category:
            params["category"] = category
        if muscles:
            params["muscles"] = ",".join(str(m) for m in muscles)
        return await self.get("/exercise/", params=params)

    async def get_exercise(self, exercise_id: int) -> dict:
        """Get details for a specific exercise."""
        return await self.get(f"/exercise/{exercise_id}/", params={"format": "json"})

    async def search_exercises(self, term: str, language: int = 2) -> dict:
        """Search exercises by name."""
        return await self.get("/exercise/search/", params={
            "term": term,
            "language": language,
            "format": "json",
        })

    async def get_exercise_info(self, exercise_id: int) -> dict:
        """Get full exercise info including images, muscles, and translations."""
        return await self.get(f"/exerciseinfo/{exercise_id}/", params={"format": "json"})

    # ─── Routines ──────────────────────────────────────────────

    async def list_routines(self) -> dict:
        """List all routines for the authenticated user."""
        return await self.get("/routine/", params={"format": "json"})

    async def create_routine(
        self,
        name: str,
        description: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Create a new workout routine."""
        data = {
            "name": name,
            "description": description,
        }
        if start_date:
            data["start_date"] = start_date
        if end_date:
            data["end_date"] = end_date
        return await self.post("/routine/", json=data)

    async def get_routine(self, routine_id: int) -> dict:
        """Get a specific routine."""
        return await self.get(f"/routine/{routine_id}/", params={"format": "json"})

    # ─── Routine Days ──────────────────────────────────────────

    async def create_day(
        self,
        routine_id: int,
        name: str,
        description: str = "",
        is_rest: bool = False,
        order: int = 1,
    ) -> dict:
        """Create a day within a routine."""
        return await self.post("/day/", json={
            "routine": routine_id,
            "name": name,
            "description": description,
            "is_rest": is_rest,
            "order": order,
        })

    # ─── Slots (Exercises within a Day) ─────────────────────────

    async def create_slot(self, day_id: int, order: int = 1) -> dict:
        """Create a slot (exercise container) within a day."""
        return await self.post("/slot/", json={
            "day": day_id,
            "order": order,
        })

    async def create_slot_entry(
        self,
        slot_id: int,
        exercise_id: int,
        order: int = 1,
        repetition_unit: int = 1,  # 1 = reps
        weight_unit: int = 1,  # 1 = kg
    ) -> dict:
        """Add an exercise to a slot."""
        return await self.post("/slot-entry/", json={
            "slot": slot_id,
            "exercise": exercise_id,
            "order": order,
            "repetition_unit": repetition_unit,
            "weight_unit": weight_unit,
        })

    # ─── Workout Logs ──────────────────────────────────────────

    async def list_workout_logs(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """List workout logs (exercise completion records)."""
        params = {"format": "json", "limit": limit}
        if date_from:
            params["date__gte"] = date_from
        if date_to:
            params["date__lte"] = date_to
        return await self.get("/workoutlog/", params=params)

    async def log_workout(
        self,
        exercise_id: int,
        reps: int,
        weight: float,
        date_str: Optional[str] = None,
        rir: Optional[int] = None,
    ) -> dict:
        """Log a single set completion."""
        data = {
            "exercise": exercise_id,
            "reps": reps,
            "weight": str(weight),
            "date": date_str or date.today().isoformat(),
        }
        if rir is not None:
            data["rir"] = rir
        return await self.post("/workoutlog/", json=data)

    # ─── Body Weight ───────────────────────────────────────────

    async def list_weight_entries(self, limit: int = 30) -> dict:
        """Get body weight history."""
        return await self.get("/weightentry/", params={
            "format": "json",
            "limit": limit,
            "ordering": "-date",
        })

    async def log_weight(self, weight_kg: float, date_str: Optional[str] = None) -> dict:
        """Log a body weight measurement."""
        return await self.post("/weightentry/", json={
            "weight": str(weight_kg),
            "date": date_str or date.today().isoformat(),
        })

    async def get_latest_weight(self) -> Optional[float]:
        """Get the most recent body weight entry."""
        try:
            result = await self.list_weight_entries(limit=1)
            entries = result.get("results", [])
            if entries:
                return float(entries[0]["weight"])
        except Exception:
            pass
        return None

    # ─── Nutrition Diary ───────────────────────────────────────

    async def list_nutrition_diary(
        self,
        plan_id: Optional[int] = None,
        date_str: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """Get nutrition diary entries."""
        params = {"format": "json", "limit": limit}
        if plan_id:
            params["plan"] = plan_id
        return await self.get("/nutritiondiary/", params=params)

    async def get_nutrition_plans(self) -> dict:
        """List nutrition plans."""
        return await self.get("/nutritionplan/", params={"format": "json"})

    # ─── Workout Log Management ──────────────────────────────

    async def delete_workout_log(self, log_id: int) -> None:
        """Delete a single workout log entry."""
        await self._request("DELETE", f"/workoutlog/{log_id}/")

    # ─── Nutrition Plan Management ────────────────────────────

    async def create_nutrition_plan(self, description: str = "AI Coach Plan") -> dict:
        """Create a nutrition plan (container for diary entries)."""
        return await self.post("/nutritionplan/", json={
            "description": description,
            "only_logging": True,
        })

    async def add_nutrition_diary_entry(
        self,
        plan_id: int,
        amount: float,
        ingredient_id: Optional[int] = None,
        weight_unit_id: Optional[int] = None,
        date_str: Optional[str] = None,
    ) -> dict:
        """Add an entry to the nutrition diary."""
        data = {
            "plan": plan_id,
            "amount": str(amount),
            "datetime": date_str or datetime.now().isoformat(),
        }
        if ingredient_id:
            data["ingredient"] = ingredient_id
        if weight_unit_id:
            data["weight_unit"] = weight_unit_id
        return await self.post("/nutritiondiary/", json=data)

    async def search_ingredient(self, term: str, language: int = 2) -> dict:
        """Search for ingredients by name."""
        return await self.get("/ingredient/", params={
            "format": "json",
            "language": language,
            "name": term,
        })

    # ─── Workout Sessions ────────────────────────────────────

    async def create_workout_session(
        self,
        routine_id: int,
        date_str: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """Create a workout session (groups log entries for a single workout)."""
        return await self.post("/workoutsession/", json={
            "routine": routine_id,
            "date": date_str or date.today().isoformat(),
            "notes": notes,
        })

    # ─── User Info ─────────────────────────────────────────────

    async def get_user_info(self) -> dict:
        """Get authenticated user's profile info from wger."""
        return await self.get("/userprofile/", params={"format": "json"})
