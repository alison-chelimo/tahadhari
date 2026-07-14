import logging
from typing import Literal

from ..clients.alerts_api import AlertsApiClient, AlertsApiError
from ..clients.icpac_client import IcpacClient, IcpacError
from ..config import get_settings
from ..schemas import Alert, AlertIn

logger = logging.getLogger("ai_layer.services.icpac_ingest")


class IcpacFeatureMappingError(Exception):
    """Raised when a WFS feature is missing a field the current mapping config needs."""


def map_feature_to_alert_in(
    feature: dict,
    *,
    geography_type: Literal["ward", "corridor"],
    geography_ref_field: str,
    rainfall_field: str,
) -> AlertIn:
    properties = feature.get("properties") or {}

    if geography_ref_field not in properties:
        raise IcpacFeatureMappingError(f"feature missing geography_ref field {geography_ref_field!r}")
    geography_ref = str(properties[geography_ref_field])

    if rainfall_field not in properties or properties[rainfall_field] is None:
        raise IcpacFeatureMappingError(f"feature missing rainfall field {rainfall_field!r}")
    try:
        rainfall_mm = float(properties[rainfall_field])
    except (TypeError, ValueError) as exc:
        raise IcpacFeatureMappingError(
            f"rainfall field {rainfall_field!r} value {properties[rainfall_field]!r} is not numeric"
        ) from exc

    return AlertIn(
        source="icpac",
        geography_type=geography_type,
        geography_ref=geography_ref,
        rainfall_mm=rainfall_mm,
        raw_payload=properties,
    )


async def run_icpac_ingest_cycle(
    icpac_client: IcpacClient | None = None,
    alerts_api_client: AlertsApiClient | None = None,
) -> list[Alert]:
    """Fetches the configured ICPAC WFS layer and ingests every mappable feature as an
    alert. Features that fail mapping (missing/malformed field) are logged and skipped
    rather than aborting the whole batch."""
    settings = get_settings()
    icpac_client = icpac_client or IcpacClient()
    alerts_api_client = alerts_api_client or AlertsApiClient()

    features = await icpac_client.fetch_layer_features(settings.icpac_layer_type_name)
    logger.info(
        "Fetched %d feature(s) from ICPAC layer %s", len(features), settings.icpac_layer_type_name
    )

    created: list[Alert] = []
    for feature in features:
        try:
            alert_in = map_feature_to_alert_in(
                feature,
                geography_type=settings.icpac_geography_type,
                geography_ref_field=settings.icpac_geography_ref_field,
                rainfall_field=settings.icpac_rainfall_field,
            )
        except IcpacFeatureMappingError as exc:
            logger.warning("Skipping unmappable ICPAC feature: %s feature=%r", exc, feature)
            continue

        try:
            alert = await alerts_api_client.ingest_alert(alert_in)
        except AlertsApiError as exc:
            logger.error("Failed to ingest ICPAC-derived alert %r: %s", alert_in, exc)
            continue

        created.append(alert)

    return created
