# Tahadhari

Tahadhari turns weather warnings into clear, specific action. Farmers, fishermen, and drivers get Telegram instructions by occupation. Commuters get flood predictions for their exact road, with a map

## Built with

Python, FastAPI, Supabase, OpenAI, GPT-4o-mini, httpx, Tenacity, Pydantic, JWT, Telegram Bot API, Google Maps API, Open-Meteo
API, ICPAC GeoNode, WFS, GeoSpatial, pytest, GitHub Actions, REST API, Uvicorn, Docker,
Railway

## Stack

- **Backend API** (`app/`): FastAPI + SQLAlchemy, Supabase Postgres in production / SQLite in-memory for tests.
- **AI layer** (`ai_layer/`): a separate package that calls OpenAI (ChatGPT) to personalize messages and classify feedback, talking to the backend API over HTTP. Message personalization (`ai_layer/services/personalizer.py`) geocodes the alert's ward/corridor name via Google Maps, pulls live Open-Meteo rainfall for it, and has the LLM weave that into a fuller message with a brief why-it-matters explanation and occupation-specific action tips — falling back to the plain filled template on any lookup/LLM failure. Claude support is kept intact but disabled — see `ai_layer/clients/claude_client.py`. Also includes an ICPAC WFS poller (`ai_layer/icpac_poll.py`) that ingests hazard data as alerts, and a location/weather poller (`ai_layer/location_poll.py`) that geocodes a user's free-text location reply via Google Maps, pulls Open-Meteo rainfall for it, and ingests it through the same alert pipeline.
- **Demo dashboard** (`dashboard/streamlit_app.py`): a Streamlit app for browsing message deliveries and road corridors without direct database access — run with `streamlit run dashboard/streamlit_app.py`.

See [`API_GUIDE.md`](./API_GUIDE.md) for the full endpoint reference.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, SUPABASE_URL, SUPABASE_KEY, SERVICE_API_KEY, JWT_SECRET_KEY, OPENAI_API_KEY, GOOGLE_MAPS_API_KEY, etc.
python -m uvicorn app.main:app --reload
```

The API is then available at `http://localhost:8000` (interactive docs at `/docs`).

### Local Telegram E2E run (recommended)

For Telegram button-flow testing, run the backend with the dev reset command enabled:

```bash
source .venv/bin/activate
set -a && source .env && set +a
export TELEGRAM_ENABLE_DEV_RESET=true
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Expose local API over HTTPS (required by Telegram webhooks):

```bash
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Then set webhook using the tunnel URL (replace `<TUNNEL_URL>`):

```bash
set -a && source .env && set +a
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
   -d "url=<TUNNEL_URL>/telegram/webhook" \
   -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
   -d 'allowed_updates=["message","callback_query"]'
```

If your production DB credentials are unavailable during local testing, you can temporarily run with SQLite:

```bash
set -a && source .env && set +a
export DATABASE_URL='sqlite:///./local_test.db'
export TELEGRAM_ENABLE_DEV_RESET=true
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Telegram onboarding flow

The Telegram bot now supports a button-first onboarding flow for Kenyan users:

- Step 1: select county from inline buttons.
- Step 2: select a major town in that county from inline buttons.
- Step 3: select occupation from inline buttons (weather-affected roles).
- Step 4: enter key asset as free text.

Additional behavior:

- `/start` does not re-register already registered users.
- `/occupation` lets a registered user amend occupation only.
- `/resetme` can clear the current Telegram test account only when dev reset is enabled.

To receive inline button clicks, Telegram webhook config must allow both update types:

- `message`
- `callback_query`

For local/dev repeat testing, run the API with:

- `TELEGRAM_ENABLE_DEV_RESET=true`

Then in Telegram:

- send `/resetme`
- send `/start`

## Deploying

The API and the `ai_layer` pollers run from a single Docker image (`Dockerfile`), so the
Telegram webhook can be pointed at a permanent hosted URL instead of a local `cloudflared`
tunnel.

### Local Docker Compose run

```bash
docker compose up --build
```

This starts three containers from the same image: `api` (the FastAPI app, port 8000),
`icpac-poll` (`python -m ai_layer.icpac_poll`), and `location-poll`
(`python -m ai_layer.location_poll`). All three read env vars from `.env`.

### Railway

Each service has its own config-as-code file so they can share one repo with different
start commands:

- `railway.api.json` — the FastAPI/webhook service
- `railway.icpac-poll.json` — the ICPAC ingestion poller
- `railway.location-poll.json` — the location/weather poller

To deploy: create one Railway service per config file (all pointing at this repo), and
under each service's Settings → Config-as-code, set the Config File Path to the matching
filename. Set the same environment variables as `.env` on each service, and point
`TAHADHARI_API_BASE_URL` on the two poller services at the `api` service's Railway URL.
Railway provisions a public HTTPS domain for the `api` service automatically — use it to
set the Telegram webhook, the same way the `<TUNNEL_URL>` is used above.

Each service auto-deploys on every push to `main` once its GitHub source/branch is
connected (Settings → Source). On each service, also enable **Settings → Source → Wait
for CI**, so Railway only deploys after `.github/workflows/ci.yml` (pytest + 80%
coverage) passes on that commit, instead of deploying straight off the push.

## Running tests

```bash
pytest
```

To check coverage the same way CI does:

```bash
pytest --cov=app --cov=ai_layer --cov-report=term-missing --cov-fail-under=80
```

Tests run fully offline: the backend suite overrides the database with in-memory SQLite,
and the `ai_layer` suite mocks all OpenAI/ICPAC/HTTP calls, so no real database, `.env`,
or API keys are required to run them locally.

Telegram webhook onboarding tests are in `app/tests/test_telegram_webhook.py` and include
county/town callback-button flows plus occupation selection and reset behavior.

## Contributing / CI

All changes land on `main` via pull request; direct pushes to `main` are not the intended
workflow.

Every PR into `main` runs the `.github/workflows/ci.yml` workflow, which:

1. Installs dependencies and runs the full `pytest` suite.
2. Fails the check if any test fails, **or** if combined coverage across `app` and
   `ai_layer` drops below **80%** (`--cov-fail-under=80`).
