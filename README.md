# Tahadhari

Tahadhari turns weather warnings into clear, specific action. Farmers, fishermen, and drivers get WhatsApp instructions by occupation. Commuters get flood predictions for their exact road, with a map

## Stack

- **Backend API** (`app/`): FastAPI + SQLAlchemy, Postgres in production / SQLite in-memory for tests.
- **AI layer** (`ai_layer/`): a separate package that calls OpenAI (ChatGPT) to personalize messages and classify feedback, talking to the backend API over HTTP. Claude support is kept intact but disabled — see `ai_layer/clients/claude_client.py`. Also includes an ICPAC WFS poller (`ai_layer/icpac_poll.py`) that ingests hazard data as alerts.

See [`API_GUIDE.md`](./API_GUIDE.md) for the full endpoint reference.

## Local setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, SERVICE_API_KEY, JWT_SECRET_KEY, etc.
uvicorn app.main:app --reload
```

The API is then available at `http://localhost:8000` (interactive docs at `/docs`).

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

## Contributing / CI

All changes land on `main` via pull request; direct pushes to `main` are not the intended
workflow.

Every PR into `main` runs the `.github/workflows/ci.yml` workflow, which:

1. Installs dependencies and runs the full `pytest` suite.
2. Fails the check if any test fails, **or** if combined coverage across `app` and
   `ai_layer` drops below **80%** (`--cov-fail-under=80`).
