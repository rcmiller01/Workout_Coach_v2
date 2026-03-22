"""
AI Fitness Coach v1 — Application Configuration
"""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import os


def _find_env_file() -> str:
    """Find .env file by searching up from this file's directory."""
    current = Path(__file__).resolve().parent  # app/
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            return str(env_path)
        current = current.parent
    return ".env"  # fallback


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Application ---
    app_name: str = "AI Fitness Coach"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-to-a-random-secret-key"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/coach.db"

    # --- wger (Workout Provider) ---
    wger_base_url: str = "http://localhost:8001/api/v2"
    wger_api_token: str = ""

    # --- Tandoor Recipes (Recipe Provider) ---
    tandoor_base_url: str = "http://localhost:8002/api"
    tandoor_api_token: str = ""

    # --- LLM Provider ---
    llm_provider: str = "ollama"  # ollama | openai | anthropic
    llm_model: str = "llama3"
    llm_base_url: str = "http://localhost:11434"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    class Config:
        env_file = _find_env_file()
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()

