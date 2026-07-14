import logging

from ..clients.alerts_api import AlertsApiClient
from ..schemas import Alert, Profile, TemplateMatch, PredictionMatch, NoMatch, SelectionResult

logger = logging.getLogger("ai_layer.services.template_selector")


async def select_content(
    alert: Alert, profile: Profile, *, client: AlertsApiClient | None = None
) -> SelectionResult:
    client = client or AlertsApiClient()
    logger.debug(
        "select_content: alert_id=%s geography_type=%s profile_id=%s language=%s",
        alert.id, alert.geography_type, profile.id, profile.language,
    )

    # "point" (per-user, coordinate-based alerts from the location/weather conversation
    # flow -- see services/location_weather.py) has no RoadSegment/corridor concept, so
    # it reuses the ward track's occupation-template matching, same as "ward".
    if alert.geography_type in ("ward", "point"):
        return await _select_template(alert, profile, client)
    if alert.geography_type == "corridor":
        return await _select_prediction(alert, profile, client)

    reason = f"unknown geography_type {alert.geography_type!r}"
    logger.warning("select_content: %s (alert_id=%s)", reason, alert.id)
    return NoMatch(alert=alert, profile=profile, reason=reason)


async def _select_template(alert: Alert, profile: Profile, client: AlertsApiClient) -> SelectionResult:
    if not profile.occupation:
        reason = "profile has no occupation; cannot match a ward-track template"
        logger.warning("select_content: %s (profile_id=%s)", reason, profile.id)
        return NoMatch(alert=alert, profile=profile, reason=reason)

    # AlertsApiError propagates (fail loud) on transient/5xx exhaustion or unexpected 4xx;
    # only "syntactically fine call, zero rows" is a NoMatch.
    templates = await client.match_templates(
        hazard_type=alert.hazard_type,
        occupation=profile.occupation,
        severity=alert.severity,
        language=profile.language,
    )

    if not templates:
        reason = (
            f"no action_template for hazard_type={alert.hazard_type!r} "
            f"occupation={profile.occupation!r} severity={alert.severity!r} "
            f"language={profile.language!r}"
        )
        logger.warning("select_content: %s", reason)
        return NoMatch(alert=alert, profile=profile, reason=reason)

    return TemplateMatch(alert=alert, profile=profile, template=templates[0])


async def _select_prediction(alert: Alert, profile: Profile, client: AlertsApiClient) -> SelectionResult:
    if not profile.route_id:
        reason = "profile has no route_id; cannot match a corridor-track prediction"
        logger.warning("select_content: %s (profile_id=%s)", reason, profile.id)
        return NoMatch(alert=alert, profile=profile, reason=reason)

    predictions = await client.predict_flooding(alert.id)

    for pred in predictions:
        if pred.segment_name == profile.route_id:
            return PredictionMatch(
                alert=alert,
                profile=profile,
                segment_name=pred.segment_name,
                risk_level=pred.risk_level,
                window_start=pred.window_start,
                window_end=pred.window_end,
                flood_prediction_id=pred.flood_prediction_id,
            )

    reason = f"no flagged segment matches profile.route_id={profile.route_id!r}"
    logger.warning("select_content: %s (alert_id=%s)", reason, alert.id)
    return NoMatch(alert=alert, profile=profile, reason=reason)
