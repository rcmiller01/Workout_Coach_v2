"""
AI Fitness Coach v1 — Tandoor Recipes Provider

Adapter for the Tandoor Recipes REST API.
Handles: recipes, meal plans, shopping lists, keywords, ingredients.

Tandoor API: https://docs.tandoor.dev/
"""
from typing import Optional
from app.providers.base import BaseProvider
from datetime import date, timedelta


class TandoorProvider(BaseProvider):
    """
    Provider adapter for Tandoor Recipes — the system of record
    for recipes, meal plans, and shopping lists.
    """

    def _auth_headers(self) -> dict[str, str]:
        # Tandoor supports both formats depending on how the token was created:
        # - Django DRF tokens (40-char SHA1): "Token <key>"
        # - Tandoor API tokens (tda_ prefix): "Bearer <key>"
        if self.api_token.startswith("tda_"):
            return {"Authorization": f"Bearer {self.api_token}"}
        return {"Authorization": f"Token {self.api_token}"}

    async def health_check(self) -> bool:
        """Check if Tandoor is reachable."""
        try:
            await self.get("/recipe/", params={"page_size": 1})
            return True
        except Exception:
            return False

    # ─── Recipes ───────────────────────────────────────────────

    async def list_recipes(
        self,
        query: Optional[str] = None,
        keywords: Optional[list[int]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List recipes with optional search and keyword filters."""
        params = {"page_size": limit, "offset": offset}
        if query:
            params["query"] = query
        if keywords:
            params["keywords"] = ",".join(str(k) for k in keywords)
        return await self.get("/recipe/", params=params)

    async def get_recipe(self, recipe_id: int) -> dict:
        """Get full recipe details including steps, ingredients, nutrition."""
        return await self.get(f"/recipe/{recipe_id}/")

    async def create_recipe(
        self,
        name: str,
        description: str = "",
        servings: int = 1,
        working_time: int = 0,
        waiting_time: int = 0,
        keywords: Optional[list[dict]] = None,
    ) -> dict:
        """Create a new recipe."""
        data = {
            "name": name,
            "description": description,
            "servings": servings,
            "working_time": working_time,
            "waiting_time": waiting_time,
        }
        if keywords:
            data["keywords"] = keywords
        return await self.post("/recipe/", json=data)

    async def update_recipe(self, recipe_id: int, data: dict) -> dict:
        """Update an existing recipe."""
        return await self.patch(f"/recipe/{recipe_id}/", json=data)

    async def import_recipe_url(self, url: str) -> dict:
        """
        Import a recipe from a URL using Tandoor's built-in importer.
        Supports many recipe websites and YouTube videos.
        """
        return await self.post("/recipe-from-source/", json={
            "url": url,
            "data": None,
        })

    # ─── Recipe Steps & Ingredients ────────────────────────────

    async def get_recipe_steps(self, recipe_id: int) -> list:
        """Get all steps for a recipe."""
        result = await self.get(f"/step/", params={"recipe": recipe_id})
        return result.get("results", result) if isinstance(result, dict) else result

    async def add_ingredient(
        self,
        step_id: int,
        food_id: int,
        amount: float,
        unit_id: Optional[int] = None,
        note: str = "",
    ) -> dict:
        """Add an ingredient to a recipe step."""
        data = {
            "step": step_id,
            "food": {"id": food_id},
            "amount": amount,
            "note": note,
        }
        if unit_id:
            data["unit"] = {"id": unit_id}
        return await self.post("/ingredient/", json=data)

    # ─── Meal Plans ────────────────────────────────────────────

    async def list_meal_plans(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict:
        """List meal plan entries."""
        params = {}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        return await self.get("/meal-plan/", params=params)

    async def create_meal_plan_entry(
        self,
        recipe_id: int,
        meal_type_id: int,
        plan_date: str,
        servings: float = 1.0,
        title: str = "",
        note: str = "",
    ) -> dict:
        """
        Create a single meal plan entry.
        Meal type IDs vary per Tandoor instance — retrieve with get_meal_types().
        """
        data = {
            "recipe": {"id": recipe_id},
            "meal_type": {"id": meal_type_id},
            "from_date": plan_date,
            "to_date": plan_date,
            "servings": servings,
            "title": title,
            "note": note,
        }
        return await self.post("/meal-plan/", json=data)

    async def delete_meal_plan_entry(self, entry_id: int) -> None:
        """Delete a meal plan entry."""
        await self.delete(f"/meal-plan/{entry_id}/")

    async def get_meal_types(self) -> list:
        """Get all meal types (breakfast, lunch, dinner, snack, etc.)."""
        result = await self.get("/meal-type/")
        return result.get("results", result) if isinstance(result, dict) else result

    async def create_meal_type(self, name: str, order: int = 0) -> dict:
        """Create a new meal type."""
        return await self.post("/meal-type/", json={"name": name, "order": order})

    # ─── Shopping Lists ────────────────────────────────────────

    async def list_shopping_entries(
        self,
        checked: Optional[bool] = None,
    ) -> dict:
        """List shopping list entries."""
        params = {}
        if checked is not None:
            params["checked"] = str(checked).lower()
        return await self.get("/shopping-list-entry/", params=params)

    async def add_shopping_entry(
        self,
        food_id: int,
        amount: float,
        unit_id: Optional[int] = None,
    ) -> dict:
        """Add an item to the shopping list."""
        data = {
            "food": {"id": food_id},
            "amount": amount,
        }
        if unit_id:
            data["unit"] = {"id": unit_id}
        return await self.post("/shopping-list-entry/", json=data)

    async def add_recipe_to_shopping(self, recipe_id: int, servings: float = 1.0) -> dict:
        """Add all ingredients from a recipe to the shopping list."""
        return await self.post(f"/recipe/{recipe_id}/shopping/", json={
            "servings": servings,
        })

    async def check_shopping_entry(self, entry_id: int, checked: bool = True) -> dict:
        """Mark a shopping list entry as checked/unchecked."""
        return await self.patch(f"/shopping-list-entry/{entry_id}/", json={
            "checked": checked,
        })

    async def delete_shopping_entry(self, entry_id: int) -> None:
        """Delete a shopping list entry."""
        await self.delete(f"/shopping-list-entry/{entry_id}/")

    async def clear_checked_shopping(self) -> None:
        """Remove all checked items from the shopping list."""
        entries = await self.list_shopping_entries(checked=True)
        items = entries.get("results", entries) if isinstance(entries, dict) else entries
        for item in items:
            await self.delete_shopping_entry(item["id"])

    # ─── Keywords (Tags) ──────────────────────────────────────

    async def list_keywords(self, query: Optional[str] = None) -> dict:
        """List recipe keywords/tags."""
        params = {}
        if query:
            params["query"] = query
        return await self.get("/keyword/", params=params)

    async def create_keyword(self, name: str, description: str = "") -> dict:
        """Create a new keyword/tag."""
        return await self.post("/keyword/", json={
            "name": name,
            "description": description,
        })

    # ─── Foods (Ingredients Database) ──────────────────────────

    async def search_foods(self, query: str) -> dict:
        """Search the food/ingredient database."""
        return await self.get("/food/", params={"query": query})

    async def get_food(self, food_id: int) -> dict:
        """Get details for a specific food item."""
        return await self.get(f"/food/{food_id}/")

    # ─── Nutrition Info ────────────────────────────────────────

    async def get_recipe_nutrition(self, recipe_id: int) -> dict:
        """
        Get calculated nutrition info for a recipe.
        Returns calories, protein, carbs, fat per serving.
        """
        return await self.get(f"/recipe/{recipe_id}/nutritional-information/")
