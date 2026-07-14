"""Periodic poller for the location/weather conversation flow: finds
RegistrationRequests waiting on a weather response and runs them through
run_location_weather_cycle() (see ai_layer/services/location_weather.py).

Requires `uvicorn app.main:app --reload` running.

Run with: python -m ai_layer.location_poll
"""

import asyncio
import logging

from .clients.alerts_api import AlertsApiClient
from .clients.google_maps_client import GoogleMapsClient
from .clients.open_meteo_client import OpenMeteoClient
from .clients.openai_client import OpenAIClient
from .config import get_settings
from .services.location_weather import run_location_weather_cycle

logger = logging.getLogger("ai_layer.location_poll")


async def poll_forever(
    google_maps_client: GoogleMapsClient,
    open_meteo_client: OpenMeteoClient,
    alerts_api_client: AlertsApiClient,
    openai_client: OpenAIClient,
) -> None:
    settings = get_settings()
    while True:
        try:
            created = await run_location_weather_cycle(
                google_maps_client, open_meteo_client, alerts_api_client, openai_client,
            )
            logger.info("Location-weather cycle produced %d message(s)", len(created))
        except Exception:
            logger.exception("Location-weather cycle failed; will retry next interval")
        await asyncio.sleep(settings.location_poll_interval_seconds)


async def main() -> None:
    google_maps_client = GoogleMapsClient()
    open_meteo_client = OpenMeteoClient()
    alerts_api_client = AlertsApiClient()
    openai_client = OpenAIClient()
    try:
        await poll_forever(google_maps_client, open_meteo_client, alerts_api_client, openai_client)
    finally:
        await google_maps_client.aclose()
        await open_meteo_client.aclose()
        await alerts_api_client.aclose()
        await openai_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
