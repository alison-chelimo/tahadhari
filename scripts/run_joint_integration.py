"""Joint integration runner for one rural and one corridor scenario.

Prerequisites:
1) API server running: uvicorn app.main:app --reload
2) Seed data loaded:
   /usr/local/bin/python3 seed_admin.py
   /usr/local/bin/python3 seed_profiles.py
   /usr/local/bin/python3 seed_segments.py
3) Env configured (.env) with SERVICE_API_KEY and TAHADHARI_SERVICE_API_KEY matching.

Run:
  /usr/local/bin/python3 scripts/run_joint_integration.py
"""

import asyncio

import httpx

from app.database import SessionLocal
from app.models import ActionTemplate
from ai_layer.clients.alerts_api import AlertsApiClient
from ai_layer.clients.claude_client import ClaudeClient
from ai_layer.clients.profiles_repo import MockProfilesRepo
from ai_layer.config import get_settings
from ai_layer.schemas import AlertIn, NoMatch
from ai_layer.services.personalizer import personalize_message
from ai_layer.services.template_selector import select_content


async def _send_delivery(message_id: int, media_url: str | None = None) -> dict:
    settings = get_settings()
    url = f"{settings.tahadhari_api_base_url.rstrip('/')}/delivery/messages/{message_id}/send"
    payload = {}
    if media_url:
        payload["media_url"] = media_url
    async with httpx.AsyncClient(timeout=20.0, headers={"X-API-Key": settings.tahadhari_service_api_key}) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def _fetch_corridor_maps(alert_id: int) -> list[dict]:
    settings = get_settings()
    url = f"{settings.tahadhari_api_base_url.rstrip('/')}/maps/alerts/{alert_id}/corridor"
    async with httpx.AsyncClient(timeout=20.0, headers={"X-API-Key": settings.tahadhari_service_api_key}) as client:
        response = await client.get(url)
        response.raise_for_status()
        body = response.json()
        return body.get("maps", [])


def _ensure_minimum_templates() -> None:
    db = SessionLocal()
    try:
        exists = db.query(ActionTemplate).filter_by(
            hazard_type="heavy_rainfall",
            occupation="farmer",
            severity="high",
            language="en",
        ).first()
        if exists:
            return

        db.add(ActionTemplate(
            hazard_type="heavy_rainfall",
            occupation="farmer",
            severity="high",
            language="en",
            template_text=(
                "Heavy rainfall expected in {ward} within 24 hours. "
                "Delay planting by 48 hours and cover stored seed before rainfall begins."
            ),
        ))
        db.commit()
    finally:
        db.close()


async def run() -> None:
    _ensure_minimum_templates()

    profiles = MockProfilesRepo()
    alerts_client = AlertsApiClient()
    claude_client = ClaudeClient()

    scenarios = [
        {
            "name": "rural_ward",
            "alert_in": AlertIn(
                source="KMD_test",
                geography_type="ward",
                geography_ref="Kisumu_Central",
                rainfall_mm=65.0,
            ),
            "profile_id": 1,
        },
        {
            "name": "urban_corridor",
            "alert_in": AlertIn(
                source="KMD_test",
                geography_type="corridor",
                geography_ref="Ngong_Road",
                rainfall_mm=45.0,
            ),
            "profile_id": 4,
        },
    ]

    try:
        for scenario in scenarios:
            print(f"\n=== Scenario: {scenario['name']} ===")
            alert = await alerts_client.ingest_alert(scenario["alert_in"])
            profile = await profiles.get_profile(scenario["profile_id"])

            selection = await select_content(alert, profile, client=alerts_client)
            if isinstance(selection, NoMatch):
                print("No match:", selection.reason)
                continue

            message = await personalize_message(
                alert,
                profile,
                selection,
                claude_client=claude_client,
                alerts_api_client=alerts_client,
            )
            print("Message created:", message.id, message.final_text)

            media_url = None
            if scenario["name"] == "urban_corridor":
                corridor_maps = await _fetch_corridor_maps(alert.id)
                for item in corridor_maps:
                    if item.get("segment_name") == getattr(selection, "segment_name", None):
                        media_url = item.get("map_url")
                        break
                if media_url:
                    print("Corridor map selected:", media_url)
                else:
                    print("No segment-specific map found; sending without media")

            delivery = await _send_delivery(message.id, media_url=media_url)
            print("Delivery result:", delivery)

    finally:
        await alerts_client.aclose()
        await claude_client.aclose()


if __name__ == "__main__":
    asyncio.run(run())
