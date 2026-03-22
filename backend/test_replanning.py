"""
Test script for Adaptive Replanning v1.

Verifies:
1. Profile Weight Logging
2. Initial Plan Generation
3. Adaptive Replanning Trigger (Weight Change)
4. Plan Revision Audit Trail
"""
import asyncio
import httpx

BASE_URL = "http://localhost:8000/api"
USER_ID = "tester_replan_1"

async def test_replanning_flow():
    # Large timeout for LLM generation
    timeout = httpx.Timeout(600.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:

        # 1. Create Profile
        print("Creating profile...")
        profile_data = {
            "user_id": USER_ID,
            "goal": "fat_loss",
            "days_per_week": 4,
            "target_calories": 2500,
            "equipment": ["dumbbell"]
        }
        await client.post(f"{BASE_URL}/profile/", json=profile_data)

        # 2. Log Initial Weight
        print("Logging initial weight...")
        await client.post(f"{BASE_URL}/profile/weight", json={
            "user_id": USER_ID,
            "weight_kg": 95.0,
            "notes": "Start"
        })

        # 3. Generate Initial Plan
        print("Generating initial plan (fast_mode)...")
        res = await client.post(f"{BASE_URL}/planning/weekly", json={
            "user_id": USER_ID,
            "fast_mode": True
        })
        plan = res.json()
        print(f"Generated Plan ID: {plan['id']}")
        
        initial_cals = plan['meal_plan'][0]['totals']['calories']
        print(f"Initial Calories: {initial_cals}")

        # 4. Log Weight Gain (Trigger for Fat Loss Replan)
        print("Logging weight gain...")
        await client.post(f"{BASE_URL}/profile/weight", json={
            "user_id": USER_ID,
            "weight_kg": 96.0, # +1kg gain
            "notes": "Gained weight, need adjustment"
        })

        # 5. Trigger Replan
        print("Triggering adaptive replan...")
        res = await client.post(f"{BASE_URL}/planning/replan?user_id={USER_ID}")
        if res.status_code != 200:
            print(f"FAILED to replan: {res.text}")
            return
            
        revision = res.json()
        print(f"Revision Created: {revision['reason']}")
        print(f"Patch applied: {revision['patch']}")

        # 6. Verify Plan Update
        res = await client.get(f"{BASE_URL}/planning/current/{USER_ID}")
        updated_plan = res.json()
        new_cals = updated_plan['meal_plan'][0]['totals']['calories']
        print(f"Updated Calories: {new_cals}")
        
        if new_cals < initial_cals:
            print("✅ SUCCESS: Calories reduced after weight gain on fat loss goal.")
        else:
            print("❌ FAILURE: Calories were not reduced correctly.")

if __name__ == "__main__":
    asyncio.run(test_replanning_flow())
