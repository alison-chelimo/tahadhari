from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""  # empty default so importing this module never crashes tests
    anthropic_model: str = "claude-sonnet-5"

    tahadhari_api_base_url: str = "http://localhost:8000"
    tahadhari_api_timeout_seconds: float = 5.0
    tahadhari_api_max_retries: int = 3
    tahadhari_service_api_key: str = ""

    claude_timeout_seconds: float = 30.0
    claude_max_retries: int = 2

    dead_letter_path: str = "ai_layer_dead_letter.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
