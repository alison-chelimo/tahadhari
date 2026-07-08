# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Tahadhari — "Climate Risk Advisor" backend API. Ingests rainfall alerts, classifies severity, predicts urban flood risk on road corridors, and matches vetted, pre-written action templates to send to at-risk users (farmers, fishermen, drivers) by occupation/language/severity.

Stack: FastAPI + SQLAlchemy 2.x (ORM, not Alembic — tables are created via `Base.metadata.create_all`) + PostgreSQL (via `psycopg2-binary`) + Pydantic v2.

## Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # note: requirements.txt is UTF-16 encoded; pip handles it, but if you regenerate it with `pip freeze > requirements.txt` on this machine, force UTF-8

# Run the API (reads DATABASE_URL from .env, not checked in)
uvicorn app.main:app --reload      # http://localhost:8000, docs at /docs

# Seed reference data (currently only road_segments; run once against a fresh DB)
python seed_segments.py
```

There is no test suite, linter, or CI config in this repo yet.

### Environment

`app/database.py` loads `DATABASE_URL` from a `.env` file at the repo root (gitignored, must be created manually) — a Postgres connection string, e.g. `postgresql://user:pass@host:5432/dbname`.

## Architecture

- `app/main.py` — FastAPI app entry point. Calls `Base.metadata.create_all(bind=engine)` on startup (no migrations framework), then mounts routers.
- `app/database.py` — engine/session setup; `get_db()` is the standard FastAPI dependency for a scoped `Session`.
- `app/models.py` — all SQLAlchemy models in one file: `Alert`, `Profile`, `ActionTemplate`, `RoadSegment`, `FloodPrediction`, `Message`, `Feedback`.
- `app/schemas.py` — Pydantic I/O schemas. Currently only `AlertIn`/`AlertOut`; the templates router defines its own inline `BaseModel` instead of using this file (inconsistent — follow existing per-router pattern unless asked to unify).
- `app/routers/` — one file per resource, included in `main.py` with a `/prefix` and OpenAPI tag:
  - `alerts.py` — `POST /alerts/ingest`, `GET /alerts/{alert_id}`, `POST /alerts/predict/{alert_id}`
  - `templates.py` — `POST /templates/`, `GET /templates/match`
  - `profiles.py` — **empty file, not wired into `main.py`**. `Profile` model exists in `models.py` but has no router/endpoints yet.

### Two parallel hazard tracks

The domain model branches on `geography_type` on `Alert`:
- `"ward"` — rural/occupation track (farmers, fishermen), keyed by ward name.
- `"corridor"` — urban track, keyed by corridor name, drives flood prediction against `RoadSegment` rows sharing that `corridor_name`.

### Business logic (currently only in `alerts.py`, no service layer)

- **Severity classification** (`classify_severity`, ingest time): `rainfall_mm >= 60` → `high`, `>= 30` → `medium`, else `low`.
- **Flood risk prediction** (`predict_flooding`, `POST /alerts/predict/{alert_id}`): only meaningful for a `corridor` alert. For every `RoadSegment` matching `alert.geography_ref` as `corridor_name`, flags it if `alert.rainfall_mm > segment.drainage_capacity_mm`, with risk `high` if `rainfall_mm > drainage_capacity_mm * 1.5` else `medium`. Writes one `FloodPrediction` row per flagged segment with a fixed 3-hour window.
- **Template matching** (`GET /templates/match`): exact-match lookup on `(hazard_type, occupation, severity, language)` against `ActionTemplate`. Templates contain `{placeholder}` tokens (e.g. `{ward}`, `{rainfall_mm}`, `{segment_name}`) that callers must fill in themselves — the API does not interpolate them. See `API_GUIDE.md` for the full placeholder → source-column mapping.

### Known gaps (MVP scope, see `API_GUIDE.md` "Known limitations")

- Only `heavy_rainfall` hazard type is supported; severity/prediction logic is not pluggable per hazard.
- Only one corridor (`Ngong_Road`) has seeded `road_segments`.
- `messages` and `feedback` tables exist in `models.py` but have no routers/endpoints.
- `profiles.py` router is an empty stub — no profile CRUD or personalization endpoint exists yet despite the `Profile` model and `API_GUIDE.md` placeholder docs referencing `profiles.occupation` etc.
- No authentication on any endpoint.

`API_GUIDE.md` is the authoritative source for request/response shapes and example payloads — check it before changing endpoint contracts.
