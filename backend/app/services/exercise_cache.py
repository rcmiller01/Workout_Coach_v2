"""
AI Fitness Coach v1 — Exercise Name → wger ID Cache

Lazily resolves exercise names to wger exercise IDs via search API.
Caches results in memory to avoid repeated API calls.
"""
import logging
from typing import Optional
from app.providers.wger import WgerProvider

logger = logging.getLogger(__name__)

# Module-level in-memory cache (survives across requests, cleared on restart)
_cache: dict[str, Optional[int]] = {}


async def resolve_exercise_id(
    wger: WgerProvider,
    exercise_name: str,
) -> Optional[int]:
    """
    Resolve an exercise name to a wger exercise ID.
    Returns None if no match found.
    """
    key = exercise_name.strip().lower()
    if key in _cache:
        return _cache[key]

    try:
        result = await wger.search_exercises(exercise_name)
        suggestions = result.get("suggestions", [])
        if suggestions:
            # Take the best match (first result)
            best = suggestions[0]
            exercise_id = best.get("data", {}).get("id")
            if exercise_id:
                _cache[key] = exercise_id
                logger.info(f"Exercise cache: '{exercise_name}' → ID {exercise_id}")
                return exercise_id

        # No match found
        _cache[key] = None
        logger.warning(f"Exercise cache: '{exercise_name}' → no match in wger")
        return None

    except Exception as e:
        logger.warning(f"Exercise cache: failed to resolve '{exercise_name}': {e}")
        return None


def get_cached_id(exercise_name: str) -> Optional[int]:
    """Get a cached exercise ID without hitting the API."""
    return _cache.get(exercise_name.strip().lower())


def clear_cache():
    """Clear the exercise cache."""
    _cache.clear()
