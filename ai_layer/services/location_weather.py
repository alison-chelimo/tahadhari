"""Orchestrates the location/weather conversation flow: discovers RegistrationRequests
that are waiting on a weather response (state=location_resolved, see
app/routers/registration.py's webhook state machine), geocodes each one's free-text
location reply via Google Maps, pulls Open-Meteo, ingests it as a "point" alert through
the existing alert/severity/template pipeline, and produces a combined
templated+LLM-personalized Message (see personalizer.py::personalize_weather_message).
"""

import logging

from ..clients.alerts_api import AlertsApiClient, AlertsApiError
from ..clients.google_maps_client import GoogleMapsClient, GoogleMapsError
from ..clients.open_meteo_client import OpenMeteoClient, OpenMeteoError
from ..clients.openai_client import OpenAIClient
from ..schemas import AlertIn, Message, TemplateMatch
from .personalizer import personalize_weather_message
from .template_selector import select_content

logger = logging.getLogger("ai_layer.services.location_weather")


async def run_location_weather_cycle(
    google_maps_client: GoogleMapsClient | None = None,
    open_meteo_client: OpenMeteoClient | None = None,
    alerts_api_client: AlertsApiClient | None = None,
    openai_client: OpenAIClient | None = None,
) -> list[Message]:
    google_maps_client = google_maps_client or GoogleMapsClient()
    open_meteo_client = open_meteo_client or OpenMeteoClient()
    alerts_api_client = alerts_api_client or AlertsApiClient()
    openai_client = openai_client or OpenAIClient()

    pending = await alerts_api_client.list_registration_requests(state="location_resolved")
    results: list[Message] = []

    for req in pending:
        if req.profile_id is None:
            # The person answered "where are you" before a full profile was created via
            # the separate, still-manual POST /profiles/ flow -- retry next cycle, don't
            # fail/dead-letter.
            logger.debug(
                "Skipping registration_request_id=%s: no profile_id yet (location "
                "answered before profile completed)", req.id,
            )
            continue

        try:
            geocode = await google_maps_client.geocode(req.raw_location_text or "")
            weather = await open_meteo_client.get_precipitation(geocode.latitude, geocode.longitude)

            alert_in = AlertIn(
                source="location_weather_poll",
                geography_type="point",
                geography_ref=geocode.formatted_address,
                rainfall_mm=weather.rainfall_mm,
                raw_payload={"lat": geocode.latitude, "lon": geocode.longitude, **weather.raw},
            )
            alert = await alerts_api_client.ingest_alert(alert_in)

            profile = await alerts_api_client.get_profile(req.profile_id)
            await alerts_api_client.update_profile_location(
                req.profile_id, geocode.latitude, geocode.longitude, geocode.formatted_address,
            )

            selection = await select_content(alert, profile, client=alerts_api_client)
            if isinstance(selection, TemplateMatch):
                message = await personalize_weather_message(
                    alert, profile, selection, weather.raw,
                    openai_client=openai_client, alerts_api_client=alerts_api_client,
                )
                results.append(message)
                await alerts_api_client.mark_registration_request_delivered(req.id)
            else:
                logger.warning(
                    "No template match for point alert_id=%s (registration_request_id=%s); "
                    "reason=%s", alert.id, req.id, getattr(selection, "reason", "unknown"),
                )
                await alerts_api_client.mark_registration_request_failed(req.id)
        except (GoogleMapsError, OpenMeteoError, AlertsApiError) as exc:
            logger.error(
                "Location-weather cycle failed for registration_request_id=%s: %s", req.id, exc,
            )
            await alerts_api_client.mark_registration_request_failed(req.id)

    return results
