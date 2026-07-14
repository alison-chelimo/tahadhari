from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from ai_layer.schemas import Alert
from ai_layer.services.icpac_ingest import (
    IcpacFeatureMappingError,
    map_feature_to_alert_in,
    run_icpac_ingest_cycle,
)


def _alert(alert_id: int = 1, geography_ref: str = "KEN") -> Alert:
    return Alert(
        id=alert_id, hazard_type="heavy_rainfall", severity="high",
        geography_type="corridor", geography_ref=geography_ref,
        rainfall_mm=12.0, created_at=datetime.now(timezone.utc),
    )


def test_map_feature_to_alert_in_happy_path():
    feature = {"properties": {"iso3": "KEN", "duration": 12.0}}
    alert_in = map_feature_to_alert_in(
        feature, geography_type="corridor", geography_ref_field="iso3", rainfall_field="duration",
    )
    assert alert_in.source == "icpac"
    assert alert_in.geography_type == "corridor"
    assert alert_in.geography_ref == "KEN"
    assert alert_in.rainfall_mm == 12.0
    assert alert_in.raw_payload == feature["properties"]


def test_map_feature_to_alert_in_missing_geography_field_raises():
    feature = {"properties": {"duration": 12.0}}
    with pytest.raises(IcpacFeatureMappingError):
        map_feature_to_alert_in(
            feature, geography_type="corridor", geography_ref_field="iso3", rainfall_field="duration",
        )


def test_map_feature_to_alert_in_missing_rainfall_field_raises():
    feature = {"properties": {"iso3": "KEN"}}
    with pytest.raises(IcpacFeatureMappingError):
        map_feature_to_alert_in(
            feature, geography_type="corridor", geography_ref_field="iso3", rainfall_field="duration",
        )


def test_map_feature_to_alert_in_non_numeric_rainfall_raises():
    feature = {"properties": {"iso3": "KEN", "duration": "not-a-number"}}
    with pytest.raises(IcpacFeatureMappingError):
        map_feature_to_alert_in(
            feature, geography_type="corridor", geography_ref_field="iso3", rainfall_field="duration",
        )


@pytest.mark.asyncio
async def test_run_icpac_ingest_cycle_ingests_all_mappable_features():
    mock_icpac = AsyncMock()
    mock_icpac.fetch_layer_features = AsyncMock(
        return_value=[
            {"properties": {"iso3": "KEN", "duration": 12.0}},
            {"properties": {"iso3": "UGA", "duration": 30.0}},
        ]
    )
    mock_alerts_api = AsyncMock()
    mock_alerts_api.ingest_alert = AsyncMock(
        side_effect=[_alert(1, "KEN"), _alert(2, "UGA")]
    )

    created = await run_icpac_ingest_cycle(mock_icpac, mock_alerts_api)

    assert len(created) == 2
    assert mock_alerts_api.ingest_alert.await_count == 2


@pytest.mark.asyncio
async def test_run_icpac_ingest_cycle_skips_unmappable_features(caplog):
    mock_icpac = AsyncMock()
    mock_icpac.fetch_layer_features = AsyncMock(
        return_value=[
            {"properties": {"iso3": "KEN"}},  # missing rainfall field
            {"properties": {"iso3": "UGA", "duration": 30.0}},
        ]
    )
    mock_alerts_api = AsyncMock()
    mock_alerts_api.ingest_alert = AsyncMock(return_value=_alert(2, "UGA"))

    created = await run_icpac_ingest_cycle(mock_icpac, mock_alerts_api)

    assert len(created) == 1
    assert mock_alerts_api.ingest_alert.await_count == 1


@pytest.mark.asyncio
async def test_run_icpac_ingest_cycle_continues_after_ingest_failure():
    from ai_layer.clients.alerts_api import AlertsApiServerError

    mock_icpac = AsyncMock()
    mock_icpac.fetch_layer_features = AsyncMock(
        return_value=[
            {"properties": {"iso3": "KEN", "duration": 12.0}},
            {"properties": {"iso3": "UGA", "duration": 30.0}},
        ]
    )
    mock_alerts_api = AsyncMock()
    mock_alerts_api.ingest_alert = AsyncMock(
        side_effect=[AlertsApiServerError(500, "boom"), _alert(2, "UGA")]
    )

    created = await run_icpac_ingest_cycle(mock_icpac, mock_alerts_api)

    assert len(created) == 1
    assert created[0].geography_ref == "UGA"
