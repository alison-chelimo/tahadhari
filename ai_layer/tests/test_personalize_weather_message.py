from datetime import datetime, timezone
from unittest.mock import AsyncMock

from ai_layer.clients.openai_client import OpenAIClientError
from ai_layer.schemas import ActionTemplate, Alert, Message, TemplateMatch
from ai_layer.services.personalizer import WeatherExplainerDraft, personalize_weather_message


def _point_alert() -> Alert:
    return Alert(
        id=1, hazard_type="heavy_rainfall", severity="high",
        geography_type="point", geography_ref="Kitengela, Kenya",
        rainfall_mm=65.0, created_at=datetime.now(timezone.utc),
    )


def _template_match(alert: Alert, profile) -> TemplateMatch:
    template = ActionTemplate(
        id=1, hazard_type="heavy_rainfall", occupation="farmer", severity="high",
        language="en", template_text="Heavy rainfall expected in {ward}. Delay planting by 48 hours.",
    )
    return TemplateMatch(alert=alert, profile=profile, template=template)


def _posted_message() -> Message:
    return Message(
        id=10, profile_id=1, alert_id=1, template_id=1, flood_prediction_id=None,
        final_text="placeholder", channel="whatsapp", delivery_status="pending",
        sent_at=datetime.now(timezone.utc),
    )


async def test_personalize_weather_message_happy_path(sample_profile_farmer):
    alert = _point_alert()
    template_match = _template_match(alert, sample_profile_farmer)

    mock_openai = AsyncMock()
    mock_openai.parse_structured = AsyncMock(
        return_value=WeatherExplainerDraft(
            message_text="Hey! Heavy rain is expected near Kitengela, Kenya soon -- hold off planting for 48 hours."
        )
    )
    mock_api = AsyncMock()
    mock_api.create_message = AsyncMock(return_value=_posted_message())

    result = await personalize_weather_message(
        alert, sample_profile_farmer, template_match, {"daily": {"precipitation_sum": [65.0]}},
        openai_client=mock_openai, alerts_api_client=mock_api,
    )

    assert result.id == 10
    mock_openai.parse_structured.assert_awaited_once()
    posted = mock_api.create_message.await_args.args[0]
    assert "hold off planting" in posted.final_text


async def test_personalize_weather_message_llm_failure_falls_back_to_template(sample_profile_farmer):
    alert = _point_alert()
    template_match = _template_match(alert, sample_profile_farmer)

    mock_openai = AsyncMock()
    mock_openai.parse_structured = AsyncMock(side_effect=OpenAIClientError("boom"))
    mock_api = AsyncMock()
    mock_api.create_message = AsyncMock(return_value=_posted_message())

    await personalize_weather_message(
        alert, sample_profile_farmer, template_match, {},
        openai_client=mock_openai, alerts_api_client=mock_api,
    )

    posted = mock_api.create_message.await_args.args[0]
    assert posted.final_text == "Heavy rainfall expected in Kitengela, Kenya. Delay planting by 48 hours."


async def test_personalize_weather_message_empty_llm_response_falls_back(sample_profile_farmer):
    alert = _point_alert()
    template_match = _template_match(alert, sample_profile_farmer)

    mock_openai = AsyncMock()
    mock_openai.parse_structured = AsyncMock(return_value=WeatherExplainerDraft(message_text="   "))
    mock_api = AsyncMock()
    mock_api.create_message = AsyncMock(return_value=_posted_message())

    await personalize_weather_message(
        alert, sample_profile_farmer, template_match, {},
        openai_client=mock_openai, alerts_api_client=mock_api,
    )

    posted = mock_api.create_message.await_args.args[0]
    assert posted.final_text == "Heavy rainfall expected in Kitengela, Kenya. Delay planting by 48 hours."
