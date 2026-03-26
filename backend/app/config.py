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
    app_env: str = "development"  # development | production
    debug: bool = True
    secret_key: str = "change-me-to-a-random-secret-key"

    # --- Auth / JWT ---
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    # --- CORS ---
    # Comma-separated list of allowed origins. "*" for dev, specific domains for prod.
    cors_origins: str = "*"

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

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    class Config:
        env_file = _find_env_file()
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
