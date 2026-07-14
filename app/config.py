from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase project URL + service_role API key, see app/supabase_client.py. Separate
    # from DATABASE_URL (the Postgres DSN, still read directly by app/database.py) --
    # this is for the supabase-py SDK (REST/Auth/Storage/Realtime), not raw SQL access.
    supabase_url: str = ""  # empty default so importing this module never crashes tests
    supabase_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
