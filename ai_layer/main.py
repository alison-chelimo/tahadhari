"""End-to-end example run of the ai_layer pipeline: ingest an alert against the real
Tahadhari API, select content (template or flood prediction), personalize it with
OpenAI, then classify a simulated feedback reply. Requires `uvicorn app.main:app
--reload` running and (ideally) a real OPENAI_API_KEY -- personalize_message and
classify_feedback both degrade gracefully rather than crash if OpenAI calls fail.

Claude is disabled in favor of OpenAI for now (see ai_layer/clients/claude_client.py,
kept intact) -- switch back by uncommenting the import below and swapping OpenAIClient
back to ClaudeClient throughout this file.

Run with: python -m ai_layer.main
"""

import asyncio
import logging

from .clients.alerts_api import AlertsApiClient
# from .clients.claude_client import ClaudeClient
from .clients.openai_client import OpenAIClient
from .clients.profiles_repo import MockProfilesRepo
from .schemas import AlertIn, NoMatch
from .services.feedback_classifier import classify_feedback
from .services.personalizer import personalize_message
from .services.template_selector import select_content

logger = logging.getLogger("ai_layer.main")

_SCENARIOS = [
    {
        "name": "ward/farmer",
        "alert_in": AlertIn(
            source="rain_gauge", geography_type="ward",
            geography_ref="Kisumu_Central", rainfall_mm=65.0,
        ),
        "profile_id": 1,
        "reply_text": "Thanks, this warning was very helpful, we moved the herd already.",
    },
    {
        "name": "corridor/driver",
        "alert_in": AlertIn(
            source="rain_gauge", geography_type="corridor",
            geography_ref="Ngong_Road", rainfall_mm=40.0,
        ),
        "profile_id": 4,
        "reply_text": "This is confusing, not sure which road you mean.",
    },
]


async def run_scenario(
    scenario: dict,
    profiles_repo: MockProfilesRepo,
    alerts_api_client: AlertsApiClient,
    openai_client: OpenAIClient,
) -> None:
    logger.info("--- scenario: %s ---", scenario["name"])

    alert = await alerts_api_client.ingest_alert(scenario["alert_in"])
    logger.info("Ingested alert id=%s severity=%s", alert.id, alert.severity)

    profile = await profiles_repo.get_profile(scenario["profile_id"])

    content = await select_content(alert, profile, client=alerts_api_client)
    if isinstance(content, NoMatch):
        logger.warning("No content matched for scenario %s: %s", scenario["name"], content.reason)
        return

    message = await personalize_message(
        alert, profile, content, openai_client=openai_client, alerts_api_client=alerts_api_client,
    )
    logger.info("Created message id=%s final_text=%r", message.id, message.final_text)

    feedback = await classify_feedback(
        message, scenario["reply_text"], openai_client=openai_client, alerts_api_client=alerts_api_client,
    )
    logger.info(
        "Classified feedback id=%s category=%s confidence=%s",
        feedback.id, feedback.feedback_type, feedback.confidence,
    )


async def main() -> None:
    profiles_repo = MockProfilesRepo()
    alerts_api_client = AlertsApiClient()
    openai_client = OpenAIClient()
    try:
        for scenario in _SCENARIOS:
            await run_scenario(scenario, profiles_repo, alerts_api_client, openai_client)
    finally:
        await alerts_api_client.aclose()
        await openai_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
