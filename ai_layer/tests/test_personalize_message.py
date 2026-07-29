from unittest.mock import AsyncMock

from ai_layer.clients.google_maps_client import GoogleMapsNoResultsError
from ai_layer.clients.openai_client import OpenAIClientError
from ai_layer.schemas import GeocodeResult, TemplateMatch, WeatherResult
from ai_layer.services.personalizer import WeatherExplainerDraft, personalize_message


def _template_match(alert, profile, template) -> TemplateMatch:
    return TemplateMatch(alert=alert, profile=profile, template=template)


async def test_personalize_message_happy_path_weaves_live_weather(
    sample_alert_ward, sample_profile_farmer, sample_template, sample_message
):
    template_match = _template_match(sample_alert_ward, sample_profile_farmer, sample_template)

    mock_openai = AsyncMock()
    mock_openai.parse_structured = AsyncMock(
        return_value=WeatherExplainerDraft(
            message_text=(
                "Heavy rainfall expected in Kisumu_Central within 24 hours -- delay "
                "planting by 48 hours. It's already raining there now, so move seedlings "
                "to higher ground and cover any stored feed."
            )
        )
    )
    mock_maps = AsyncMock()
    mock_maps.geocode = AsyncMock(
        return_value=GeocodeResult(latitude=-0.1, longitude=34.75, formatted_address="Kisumu Central, Kenya")
    )
    mock_meteo = AsyncMock()
    mock_meteo.get_precipitation = AsyncMock(
        return_value=WeatherResult(rainfall_mm=12.0, raw={"daily": {"precipitation_sum": [12.0]}})
    )
    mock_api = AsyncMock()
    mock_api.create_message = AsyncMock(return_value=sample_message)

    result = await personalize_message(
        sample_alert_ward, sample_profile_farmer, template_match,
        openai_client=mock_openai, alerts_api_client=mock_api,
        google_maps_client=mock_maps, open_meteo_client=mock_meteo,
    )

    assert result.id == 10
    mock_maps.geocode.assert_awaited_once_with("Kisumu_Central")
    mock_meteo.get_precipitation.assert_awaited_once_with(-0.1, 34.75)
    mock_openai.parse_structured.assert_awaited_once()
    call_kwargs = mock_openai.parse_structured.await_args.kwargs
    assert "precipitation_sum" in call_kwargs["user_content"]
    posted = mock_api.create_message.await_args.args[0]
    assert "move seedlings" in posted.final_text


async def test_personalize_message_geocoding_failure_still_enriches_without_weather(
    sample_alert_ward, sample_profile_farmer, sample_template, sample_message
):
    template_match = _template_match(sample_alert_ward, sample_profile_farmer, sample_template)

    mock_openai = AsyncMock()
    mock_openai.parse_structured = AsyncMock(
        return_value=WeatherExplainerDraft(
            message_text="Heavy rainfall expected in Kisumu_Central within 24 hours. Delay planting by 48 hours."
        )
    )
    mock_maps = AsyncMock()
    mock_maps.geocode = AsyncMock(side_effect=GoogleMapsNoResultsError("no results"))
    mock_meteo = AsyncMock()
    mock_api = AsyncMock()
    mock_api.create_message = AsyncMock(return_value=sample_message)

    await personalize_message(
        sample_alert_ward, sample_profile_farmer, template_match,
        openai_client=mock_openai, alerts_api_client=mock_api,
        google_maps_client=mock_maps, open_meteo_client=mock_meteo,
    )

    mock_meteo.get_precipitation.assert_not_awaited()
    call_kwargs = mock_openai.parse_structured.await_args.kwargs
    assert "raw_weather=None" in call_kwargs["user_content"]


async def test_personalize_message_llm_failure_falls_back_to_template(
    sample_alert_ward, sample_profile_farmer, sample_template, sample_message
):
    template_match = _template_match(sample_alert_ward, sample_profile_farmer, sample_template)

    mock_openai = AsyncMock()
    mock_openai.parse_structured = AsyncMock(side_effect=OpenAIClientError("boom"))
    mock_maps = AsyncMock()
    mock_maps.geocode = AsyncMock(side_effect=GoogleMapsNoResultsError("no results"))
    mock_meteo = AsyncMock()
    mock_api = AsyncMock()
    mock_api.create_message = AsyncMock(return_value=sample_message)

    await personalize_message(
        sample_alert_ward, sample_profile_farmer, template_match,
        openai_client=mock_openai, alerts_api_client=mock_api,
        google_maps_client=mock_maps, open_meteo_client=mock_meteo,
    )

    posted = mock_api.create_message.await_args.args[0]
    assert posted.final_text == (
        "Heavy rainfall expected in Kisumu_Central within 24 hours. Delay planting by 48 hours."
    )
