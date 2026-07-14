import logging
from unittest.mock import AsyncMock

import pytest

from ai_layer.schemas import NoMatch, TemplateMatch, PredictionRecord
from ai_layer.services.template_selector import select_content


async def test_select_content_ward_no_match(sample_alert_ward, sample_profile_farmer_sw, caplog):
    mock_client = AsyncMock()
    mock_client.match_templates = AsyncMock(return_value=[])

    with caplog.at_level(logging.WARNING):
        result = await select_content(sample_alert_ward, sample_profile_farmer_sw, client=mock_client)

    assert isinstance(result, NoMatch)
    assert "sw" in result.reason
    assert any(record.levelno == logging.WARNING for record in caplog.records)


async def test_select_content_ward_match(sample_alert_ward, sample_profile_farmer, sample_template):
    mock_client = AsyncMock()
    mock_client.match_templates = AsyncMock(return_value=[sample_template])

    result = await select_content(sample_alert_ward, sample_profile_farmer, client=mock_client)

    assert isinstance(result, TemplateMatch)
    assert result.template == sample_template
    mock_client.match_templates.assert_awaited_once_with(
        hazard_type="heavy_rainfall", occupation="farmer", severity="high", language="en",
    )


async def test_select_content_point_match(sample_alert_ward, sample_profile_farmer, sample_template):
    from ai_layer.schemas import Alert

    point_alert = Alert(
        id=5, hazard_type=sample_alert_ward.hazard_type, severity=sample_alert_ward.severity,
        geography_type="point", geography_ref="Kitengela, Kenya",
        rainfall_mm=sample_alert_ward.rainfall_mm, created_at=sample_alert_ward.created_at,
    )
    mock_client = AsyncMock()
    mock_client.match_templates = AsyncMock(return_value=[sample_template])

    result = await select_content(point_alert, sample_profile_farmer, client=mock_client)

    assert isinstance(result, TemplateMatch)
    assert result.template == sample_template


async def test_select_content_corridor_no_match(sample_alert_ward):
    from ai_layer.schemas import Alert, Profile

    corridor_alert = Alert(
        id=2, hazard_type="heavy_rainfall", severity="medium",
        geography_type="corridor", geography_ref="Ngong_Road",
        rainfall_mm=40.0, created_at=sample_alert_ward.created_at,
    )
    driver_profile = Profile(
        id=4, phone_number="+254712345004", channel="whatsapp", language="en",
        user_type="urban", occupation="driver", route_id="Adams_Arcade", key_asset="matatu_route_46",
    )

    mock_client = AsyncMock()
    mock_client.predict_flooding = AsyncMock(
        return_value=[PredictionRecord(segment_name="Yaya_Centre", risk_level="medium")]
    )

    result = await select_content(corridor_alert, driver_profile, client=mock_client)

    assert isinstance(result, NoMatch)
    assert "Adams_Arcade" in result.reason
