"""Supabase SDK client (REST/Auth/Storage/Realtime) -- separate from app/database.py's
SQLAlchemy engine, which still talks to the same Supabase project over raw Postgres.
Not wired into any router yet; scaffolding for future Storage/Auth/Realtime work."""

from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)
