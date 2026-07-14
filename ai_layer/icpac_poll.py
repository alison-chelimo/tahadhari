"""Periodic poller that pulls the configured ICPAC WFS layer and ingests it as alerts
against the real Tahadhari API. See Settings.icpac_* in ai_layer/config.py for which
layer/fields are used -- the shipped default (geonode:gha_dr_events) is a historical
drought-event layer confirmed reachable over WFS, chosen so this runs end-to-end out of
the box; it is NOT a live rainfall-alert feed. Swap the config once ICPAC publishes one.

Requires `uvicorn app.main:app --reload` running.

Run with: python -m ai_layer.icpac_poll
"""

import asyncio
import logging

from .clients.alerts_api import AlertsApiClient
from .clients.icpac_client import IcpacClient
from .config import get_settings
from .services.icpac_ingest import run_icpac_ingest_cycle

logger = logging.getLogger("ai_layer.icpac_poll")


async def poll_forever(icpac_client: IcpacClient, alerts_api_client: AlertsApiClient) -> None:
    settings = get_settings()
    while True:
        try:
            created = await run_icpac_ingest_cycle(icpac_client, alerts_api_client)
            logger.info("ICPAC ingest cycle created %d alert(s)", len(created))
        except Exception:
            logger.exception("ICPAC ingest cycle failed; will retry next interval")
        await asyncio.sleep(settings.icpac_poll_interval_seconds)


async def main() -> None:
    icpac_client = IcpacClient()
    alerts_api_client = AlertsApiClient()
    try:
        await poll_forever(icpac_client, alerts_api_client)
    finally:
        await icpac_client.aclose()
        await alerts_api_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
