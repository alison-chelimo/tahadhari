from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from ai_layer.clients.google_maps_client import GoogleMapsNoResultsError
from ai_layer.schemas import (
    ActionTemplate,
    Alert,
    GeocodeResult,
    Message,
    NoMatch,
    Profile,
    RegistrationRequest,
    TemplateMatch,
    WeatherResult,
)
from ai_layer.services.location_weather import run_location_weather_cycle


def _pending_request(**overrides) -> RegistrationRequest:
    defaults = dict(
        id=1, phone_number="+254712345001", channel="whatsapp", raw_text="REGISTER",
        matched_keyword="register", profile_id=1, state="location_resolved",
        raw_location_text="Kitengela", resolved_at=None, created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return RegistrationRequest(**defaults)


def _profile() -> Profile:
    return Profile(
        id=1, phone_number="+254712345001", channel="whatsapp", language="en",
        user_type="rural", occupation="farmer", ward=None, key_asset="maize_farm",
    )


def _alert() -> Alert:
    return Alert(
        id=1, hazard_type="heavy_rainfall", severity="high",
        geography_type="point", geography_ref="Kitengela, Kenya",
        rainfall_mm=65.0, created_at=datetime.now(timezone.utc),
    )


def _template_match(alert: Alert, profile: Profile) -> TemplateMatch:
    template = ActionTemplate(
        id=1, hazard_type="heavy_rainfall", occupation="farmer", severity="high",
        language="en", template_text="Heavy rainfall expected in {ward}.",
    )
    return TemplateMatch(alert=alert, profile=profile, template=template)


def _message() -> Message:
    return Message(
        id=10, profile_id=1, alert_id=1, template_id=1, flood_prediction_id=None,
        final_text="Heavy rainfall expected near Kitengela.", channel="whatsapp",
        delivery_status="pending", sent_at=datetime.now(timezone.utc),
    )


def _clients(pending=None, geocode_side_effect=None):
    alerts_api_client = AsyncMock()
    alerts_api_client.list_registration_requests = AsyncMock(return_value=pending or [_pending_request()])
    alerts_api_client.ingest_alert = AsyncMock(return_value=_alert())
    alerts_api_client.get_profile = AsyncMock(return_value=_profile())
    alerts_api_client.update_profile_location = AsyncMock(return_value=_profile())
    alerts_api_client.mark_registration_request_delivered = AsyncMock()
    alerts_api_client.mark_registration_request_failed = AsyncMock()

    google_maps_client = AsyncMock()
    if geocode_side_effect is not None:
        google_maps_client.geocode = AsyncMock(side_effect=geocode_side_effect)
    else:
        google_maps_client.geocode = AsyncMock(
            return_value=GeocodeResult(latitude=-1.4536, longitude=36.9721, formatted_address="Kitengela, Kenya")
        )

    open_meteo_client = AsyncMock()
    open_meteo_client.get_precipitation = AsyncMock(return_value=WeatherResult(rainfall_mm=65.0, raw={"daily": {}}))

    openai_client = AsyncMock()

    return google_maps_client, open_meteo_client, alerts_api_client, openai_client


@pytest.mark.asyncio
async def test_happy_path_produces_message(mocker):
    google_maps_client, open_meteo_client, alerts_api_client, openai_client = _clients()
    alert = _alert()
    profile = _profile()
    mocker.patch(
        "ai_layer.services.location_weather.select_content",
        new=AsyncMock(return_value=_template_match(alert, profile)),
    )
    mocker.patch(
        "ai_layer.services.location_weather.personalize_weather_message",
        new=AsyncMock(return_value=_message()),
    )

    results = await run_location_weather_cycle(google_maps_client, open_meteo_client, alerts_api_client, openai_client)

    assert len(results) == 1
    assert results[0].id == 10
    alerts_api_client.mark_registration_request_delivered.assert_awaited_once_with(1)
    alerts_api_client.mark_registration_request_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_request_with_no_profile_id():
    google_maps_client, open_meteo_client, alerts_api_client, openai_client = _clients(
        pending=[_pending_request(profile_id=None)]
    )

    results = await run_location_weather_cycle(google_maps_client, open_meteo_client, alerts_api_client, openai_client)

    assert results == []
    alerts_api_client.mark_registration_request_failed.assert_not_awaited()
    alerts_api_client.mark_registration_request_delivered.assert_not_awaited()
    google_maps_client.geocode.assert_not_awaited()


@pytest.mark.asyncio
async def test_geocode_failure_marks_request_failed():
    google_maps_client, open_meteo_client, alerts_api_client, openai_client = _clients(
        geocode_side_effect=GoogleMapsNoResultsError("no results")
    )

    results = await run_location_weather_cycle(google_maps_client, open_meteo_client, alerts_api_client, openai_client)

    assert results == []
    alerts_api_client.mark_registration_request_failed.assert_awaited_once_with(1)
    alerts_api_client.ingest_alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_template_match_marks_request_failed(mocker):
    google_maps_client, open_meteo_client, alerts_api_client, openai_client = _clients()
    alert = _alert()
    profile = _profile()
    mocker.patch(
        "ai_layer.services.location_weather.select_content",
        new=AsyncMock(return_value=NoMatch(alert=alert, profile=profile, reason="no template")),
    )
    personalize_mock = mocker.patch(
        "ai_layer.services.location_weather.personalize_weather_message", new=AsyncMock()
    )

    results = await run_location_weather_cycle(google_maps_client, open_meteo_client, alerts_api_client, openai_client)

    assert results == []
    personalize_mock.assert_not_awaited()
    alerts_api_client.mark_registration_request_failed.assert_awaited_once_with(1)
    alerts_api_client.mark_registration_request_delivered.assert_not_awaited()
