import asyncio
from app.database import init_db
from app.models.user import User, UserProfile, WeightEntry
from app.models.plan import WeeklyPlan, PlanRevision

async def main():
    print("Initializing Database with Updated Schema...")
    await init_db()
    print("Database Initialized Successfully.")

if __name__ == "__main__":
    asyncio.run(main())
