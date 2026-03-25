"""
AI Fitness Coach v1 — Database Setup
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import os


# Ensure data directory exists (only for SQLite)
if "sqlite" in settings.database_url:
    os.makedirs("data", exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def init_db():
    """Create all database tables and add any missing columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add columns that may be missing from existing tables (safe ALTER TABLE)
    _alter_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS workout_notes TEXT",
        "ALTER TABLE meal_logs ADD COLUMN IF NOT EXISTS synced_to_wger VARCHAR(20) DEFAULT 'pending'",
        "ALTER TABLE weight_entries ADD COLUMN IF NOT EXISTS synced_to_wger VARCHAR(20) DEFAULT 'pending'",
    ]
    async with engine.begin() as conn:
        for stmt in _alter_statements:
            try:
                from sqlalchemy import text
                await conn.execute(text(stmt))
            except Exception:
                pass  # Column already exists or DB doesn't support IF NOT EXISTS


async def get_db() -> AsyncSession:
    """Dependency: yield a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
