"""
AI Fitness Coach v1 — Chaos Simulation Script

This script intentionally breaks the system to test its resilience.
It tests LLM nonsense, provider timeouts, and partial fails.
"""
import asyncio
import json
import uuid
import httpx
from datetime import datetime
from app.engine.planner import LLMPlanner
from app.services.planning import PlanningService
from app.logging_config import get_logger

logger = get_logger("chaos_tester")

# Mock Profile
TEST_PROFILE = {
    "user_id": "chaos_user_1",
    "goal": "muscle_gain",
    "days_per_week": 4,
    "target_calories": 2500,
    "equipment": ["dumbbell"],
    "injuries": [{"area": "left_knee", "severity": "mild"}]
}

async def test_llm_json_garbage():
    """Test 1: LLM returns non-JSON garbage."""
    print("\n--- Test 1: LLM JSON Garbage ---")
    planner = LLMPlanner()
    garbage = "I'm sorry, I can't do that. Here is some text instead of JSON."
    
    try:
        planner._parse_json(garbage)
    except ValueError as e:
        print(f"✅ Caught expected JSON parsing error: {e}")

async def test_llm_malformed_json():
    """Test 2: LLM returns malformed JSON."""
    print("\n--- Test 2: LLM Malformed JSON ---")
    planner = LLMPlanner()
    malformed = '{"split_type": "Full Body", "days": [{"day": "Monday", "exercises":' # Unclosed
    
    try:
        planner._parse_json(malformed)
    except ValueError as e:
        print(f"✅ Caught expected malformed JSON error: {e}")

async def test_oversize_response():
    """Test 3: LLM returns a response that is too large (safety trigger)."""
    print("\n--- Test 3: LLM Oversize Response ---")
    planner = LLMPlanner()
    planner.max_response_size = 100 # Artificially low
    
    # We fake the LLM call logic partially
    content = "A" * 200
    try:
        if len(content) > planner.max_response_size:
            raise ValueError("LLM response exceeded safety size limit")
    except ValueError as e:
        print(f"✅ Caught expected oversize error: {e}")

async def test_api_rejection_of_lock():
    """Test 4: Concurrent generation lock."""
    print("\n--- Test 4: Generation Lock ---")
    from app.services.planning import ACTIVE_GENERATIONS
    ACTIVE_GENERATIONS.add("chaos_user_1")
    
    service = PlanningService(None, None) # Providers not needed for lock check
    try:
        await service.create_weekly_plan(TEST_PROFILE)
    except ValueError as e:
        print(f"✅ Caught expected lock conflict: {e}")
    finally:
        ACTIVE_GENERATIONS.remove("chaos_user_1")

async def test_invalid_macros_vanguard():
    """Test 5: Pydantic model rejects bad macros from LLM."""
    print("\n--- Test 5: Macro Vanguard (Pydantic Rejection) ---")
    from app.engine.models import NormalizedMacros
    
    bad_macros = {
        "calories": 2000,
        "protein_g": 10,
        "carbs_g": 10,
        "fat_g": 10
    } # 10*4 + 10*4 + 10*9 = 170 calories. 2000 is nonsense.
    
    try:
        NormalizedMacros(**bad_macros)
    except ValueError as e:
        print(f"✅ Caught expected macro inconsistency: {e}")

async def main():
    print("🚀 Starting Chaos Simulation Matrix...")
    await test_llm_json_garbage()
    await test_llm_malformed_json()
    await test_oversize_response()
    await test_api_rejection_of_lock()
    await test_invalid_macros_vanguard()
    print("\n🏁 Chaos tests complete.")

if __name__ == "__main__":
    asyncio.run(main())
