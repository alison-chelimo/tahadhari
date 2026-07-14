from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Claude is currently disabled in favor of OpenAI (see clients/openai_client.py) --
    # these fields and claude_client.py are kept intact so switching back is a small diff.
    anthropic_api_key: str = ""  # empty default so importing this module never crashes tests
    anthropic_model: str = "claude-sonnet-5"
    claude_timeout_seconds: float = 30.0
    claude_max_retries: int = 2

    openai_api_key: str = ""  # empty default so importing this module never crashes tests
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2

    tahadhari_api_base_url: str = "http://localhost:8000"
    tahadhari_api_timeout_seconds: float = 5.0
    tahadhari_api_max_retries: int = 3
    tahadhari_service_api_key: str = ""

    # ICPAC GeoNode (geoportal.icpac.net) WFS polling. No layer on that portal is a true
    # live rainfall-alert feed today -- the default type_name/fields below point at
    # geonode:gha_dr_events, a historical drought-event layer confirmed reachable over
    # WFS, so the pipeline runs end-to-end out of the box. Swap these once ICPAC
    # publishes a real live hazard layer; see ai_layer/clients/icpac_client.py.
    icpac_base_url: str = "https://geoportal.icpac.net"
    icpac_layer_type_name: str = "geonode:gha_dr_events"
    icpac_geography_type: Literal["ward", "corridor"] = "corridor"
    icpac_geography_ref_field: str = "iso3"
    icpac_rainfall_field: str = "duration"  # placeholder numeric field -- see comment above
    icpac_timeout_seconds: float = 10.0
    icpac_max_retries: int = 3
    icpac_poll_interval_seconds: float = 3600.0

    # Open-Meteo (open-meteo.com) -- free, no-API-key REST weather API queried per
    # lat/lon coordinate. Used by the location/weather conversation flow (see
    # ai_layer/services/location_weather.py), not by the ICPAC poller above.
    open_meteo_base_url: str = "https://api.open-meteo.com"
    open_meteo_timeout_seconds: float = 10.0
    open_meteo_max_retries: int = 3

    # Google Maps Geocoding API -- resolves a user's free-text location reply (e.g.
    # "Kitengela") to lat/lon before it's handed to Open-Meteo.
    google_maps_api_key: str = ""  # empty default so importing this module never crashes tests
    google_maps_base_url: str = "https://maps.googleapis.com"
    google_maps_timeout_seconds: float = 10.0
    google_maps_max_retries: int = 3

    # Interval for ai_layer/location_poll.py -- much shorter than icpac_poll_interval_seconds
    # since this is a per-user, near-real-time reply rather than a scheduled bulk sweep.
    location_poll_interval_seconds: float = 300.0

    dead_letter_path: str = "ai_layer_dead_letter.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
