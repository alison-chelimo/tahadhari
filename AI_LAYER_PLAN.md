# Plan: `ai_layer` — AI & Language Layer for Tahadhari

## Context

Tahadhari turns rainfall/flood alerts into personalized WhatsApp/SMS messages for two
audiences: rural occupation-track users (farmers, fishermen, drivers) who get a vetted,
pre-written action template, and urban corridor-track users who get a flood-risk
prediction for their road segment. Alison ("Person One") built the core API — alert
ingestion, severity classification, flood prediction, template matching — but two
pieces are explicitly missing: nothing selects/personalizes/sends a message from that
data, and the `messages`/`feedback` tables have no API surface at all (empty stub in
`app/routers/profiles.py` aside, `messages.py`/`feedback.py` don't exist yet).

This plan builds the AI layer's scope: a standalone `ai_layer` package that (a) calls
Alison's real API to pick the right template or prediction, (b) fills in placeholders
and uses Claude to polish the final message text (or generate a flood-warning sentence
from structured fields), (c) classifies free-text WhatsApp feedback replies into fixed
categories via Claude, and (d) the two missing FastAPI endpoints (`/messages`,
`/feedback`) those services need to persist their output — built to the same standard
as the rest of the app, with real validation and error handling. Mock profile data
stands in for the not-yet-built `profiles` endpoint behind a swappable interface.

**Decisions already confirmed with the user:**
- Claude model: `claude-sonnet-5` (near-Opus quality, better cost/latency for
  production message volume than Opus 4.8), configurable via `ANTHROPIC_MODEL`, never
  hardcoded elsewhere.
- Git: create a **new branch off `main`**, commit incrementally using **Conventional
  Commits** (`feat:`, `fix:`, `test:`, etc.) as pieces land. **No commit trailers**
  (no `Claude-Session:` or similar footers on any commit in this work).

**A gap discovered during planning, now folded into scope:** `POST
/alerts/predict/{alert_id}` (in Alison's `app/routers/alerts.py`) currently returns
only `{"segment": ..., "risk": ...}` per flagged segment — no `window_start`/
`window_end`/`flood_prediction_id`, even though the `FloodPrediction` row already
has those columns (it just isn't surfacing them in the response dict). Per user
direction, this plan **extends that endpoint** to include them — see §1a below —
so `ai_layer`'s urban track gets real window/id data instead of always `None`.
This is a small, additive, backward-compatible change (adds three keys to each
prediction dict; the existing `segment`/`risk` keys are untouched).

## Scope boundaries (explicit, to avoid drift)

- No actual WhatsApp/SMS delivery is implemented — `/messages` only persists a row;
  `delivery_status` stays at its DB default (`"pending"`).
- `app/routers/profiles.py` stays untouched/unwired — mock profile data lives entirely
  inside `ai_layer`, behind an interface a future `ApiProfilesRepo` can implement.
- No changes to `app/routers/alerts.py` or `app/routers/templates.py` beyond what's
  needed to import from an updated `app/schemas.py` — their existing bugs (no
  `HTTPException` anywhere, silent `None` returns) are not being fixed here.

## Package layout

```
ai_layer/                      # new, repo root, sibling to app/
    __init__.py
    config.py                    # pydantic-settings
    clients/
        __init__.py
        alerts_api.py             # async httpx client: /alerts, /templates, /messages, /feedback
        claude_client.py          # wraps AsyncAnthropic (claude-sonnet-5)
        profiles_repo.py          # ProfilesRepo ABC + MockProfilesRepo + mock data
    schemas.py                    # all ai_layer-side Pydantic models
    dead_letter.py                # shared JSONL fallback for both services
    services/
        __init__.py
        template_selector.py      # select_content()
        personalizer.py           # build_placeholder_values/fill_placeholders/personalize_message
        feedback_classifier.py    # classify_feedback()
    tests/
        conftest.py                # shared fixtures
        test_placeholder_filling.py
        test_template_selector.py
        test_feedback_classifier.py
    main.py                       # end-to-end example run
seed_profiles.py                 # repo root, sibling to seed_segments.py (see below)
.env.example                     # repo root, new
```

Plus edits to Alison's `app/`: `app/schemas.py`, two new files
`app/routers/messages.py` / `app/routers/feedback.py`, and `app/main.py` (register the
two new routers — same pattern as the existing `include_router` calls).

## 1. Alison's `app/` — new endpoints

### 1a. `app/routers/alerts.py` (edit — extend `predict_flooding` to return window/id data)

Current implementation already creates a `FloodPrediction` row per flagged segment
with `window_start`/`window_end` — it just doesn't include them in the response dict.
Minimal, additive change to the return statement only (no change to the
flagging/risk logic):

```python
@router.post("/predict/{alert_id}")
def predict_flooding(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    segments = db.query(RoadSegment).filter_by(corridor_name=alert.geography_ref).all()

    predictions = []
    flagged_segments = []
    for seg in segments:
        if alert.rainfall_mm > seg.drainage_capacity_mm:
            risk = "high" if alert.rainfall_mm > seg.drainage_capacity_mm * 1.5 else "medium"
            pred = FloodPrediction(
                alert_id=alert.id,
                segment_id=seg.id,
                risk_level=risk,
                window_start=datetime.utcnow(),
                window_end=datetime.utcnow() + timedelta(hours=3),
            )
            db.add(pred)
            predictions.append(pred)
            flagged_segments.append(seg)

    db.commit()
    return {
        "flagged_segments": len(predictions),
        "predictions": [
            {
                "flood_prediction_id": p.id,
                "segment": seg.segment_name,
                "risk": p.risk_level,
                "window_start": p.window_start,
                "window_end": p.window_end,
            }
            for seg, p in zip(flagged_segments, predictions)
        ]
    }
```

`p.id`/`p.window_start`/`p.window_end` are accessible after `db.commit()` without an
explicit `db.refresh(p)` per object — SQLAlchemy's default `expire_on_commit=True`
lazily reloads each attribute from the still-open session on next access (same
pattern the file already relies on implicitly). FastAPI serializes the `datetime`
values to ISO 8601 strings automatically via `jsonable_encoder`, same as it already
does for `AlertOut.created_at` — no explicit formatting needed.

**Also update `API_GUIDE.md`**: its example response for `POST
/alerts/predict/{alert_id}` (section 3) currently shows only `segment`/`risk` per
prediction — update it to include `flood_prediction_id`/`window_start`/`window_end`,
per `CLAUDE.md`'s own instruction to keep that file authoritative for response shapes.

### `app/schemas.py` (append after `AlertOut`, keep existing `Config: from_attributes`
style — this file uses Pydantic v2's `class Config`, not `model_config=`, stay
consistent)

```python
from enum import Enum

class MessageIn(BaseModel):
    profile_id: int
    alert_id: int
    template_id: Optional[int] = None
    flood_prediction_id: Optional[int] = None
    final_text: str
    channel: str  # "whatsapp" or "sms" — plain str, matching this file's existing
                  # loose-typing convention (AlertIn.geography_type is also a plain str)

class MessageOut(BaseModel):
    id: int
    profile_id: int
    alert_id: int
    template_id: Optional[int]
    flood_prediction_id: Optional[int]
    final_text: str
    channel: str
    delivery_status: str
    sent_at: datetime
    class Config:
        from_attributes = True

class FeedbackType(str, Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    INCORRECT_LOCATION = "incorrect_location"
    INCORRECT_TIMING = "incorrect_timing"
    UNCLEAR = "unclear"
    OTHER = "other"

class FeedbackIn(BaseModel):
    message_id: int
    profile_id: int
    feedback_type: FeedbackType
    feedback_text: Optional[str] = None

class FeedbackOut(BaseModel):
    id: int
    message_id: int
    profile_id: int
    feedback_type: str
    feedback_text: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True
```

### `app/routers/messages.py` (new — sync `def`, not async, matching every other
router in this app; uses `Depends(get_db)` exactly like `alerts.py`)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ..database import get_db
from ..models import Message, Profile, Alert, ActionTemplate, FloodPrediction
from ..schemas import MessageIn, MessageOut

router = APIRouter()

@router.post("/", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageIn, db: Session = Depends(get_db)):
    if not db.query(Profile).filter(Profile.id == payload.profile_id).first():
        raise HTTPException(status_code=404, detail=f"Profile {payload.profile_id} not found")
    if not db.query(Alert).filter(Alert.id == payload.alert_id).first():
        raise HTTPException(status_code=404, detail=f"Alert {payload.alert_id} not found")
    if payload.template_id is not None and not db.query(ActionTemplate).filter(ActionTemplate.id == payload.template_id).first():
        raise HTTPException(status_code=404, detail=f"ActionTemplate {payload.template_id} not found")
    if payload.flood_prediction_id is not None and not db.query(FloodPrediction).filter(FloodPrediction.id == payload.flood_prediction_id).first():
        raise HTTPException(status_code=404, detail=f"FloodPrediction {payload.flood_prediction_id} not found")

    db_message = Message(**payload.model_dump())
    try:
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist message")
    return db_message

@router.get("/{message_id}", response_model=MessageOut)
def get_message(message_id: int, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
    return message
```

Design choice: **every** missing referenced entity (`profile_id`, `alert_id`,
`template_id`, `flood_prediction_id`) is a **404** — 422 stays reserved for
Pydantic body-shape errors, which FastAPI already handles automatically. Insert is
wrapped in try/except with rollback per the "transaction with rollback on failure"
requirement.

### `app/routers/feedback.py` (new — same pattern)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ..database import get_db
from ..models import Feedback, Message, Profile
from ..schemas import FeedbackIn, FeedbackOut

router = APIRouter()

@router.post("/", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackIn, db: Session = Depends(get_db)):
    if not db.query(Message).filter(Message.id == payload.message_id).first():
        raise HTTPException(status_code=404, detail=f"Message {payload.message_id} not found")
    if not db.query(Profile).filter(Profile.id == payload.profile_id).first():
        raise HTTPException(status_code=404, detail=f"Profile {payload.profile_id} not found")

    db_feedback = Feedback(
        message_id=payload.message_id, profile_id=payload.profile_id,
        feedback_type=payload.feedback_type.value, feedback_text=payload.feedback_text,
    )
    try:
        db.add(db_feedback)
        db.commit()
        db.refresh(db_feedback)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist feedback")
    return db_feedback

@router.get("/{feedback_id}", response_model=FeedbackOut)
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} not found")
    return feedback
```

**Design decision flagged for review:** the build brief says `GET
/feedback/{message_id}`, which is ambiguous — retrieval by feedback's own id, or "all
feedback for this message"? Implementing the former (`{feedback_id}`) for REST
consistency with `GET /messages/{message_id}` (both retrieve-by-own-primary-key). If
lookup-by-message is actually wanted, that's a different route shape
(`GET /feedback/by-message/{message_id}`, returning a list) — flag during review if so.

### `app/main.py` (edit — add alongside the two existing `include_router` calls)

```python
from .routers import alerts, templates, messages, feedback
...
app.include_router(messages.router, prefix="/messages", tags=["messages"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
```

## 2. `ai_layer/config.py`

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""              # empty default so import never crashes tests
    anthropic_model: str = "claude-sonnet-5"

    tahadhari_api_base_url: str = "http://localhost:8000"
    tahadhari_api_timeout_seconds: float = 5.0
    tahadhari_api_max_retries: int = 3

    claude_timeout_seconds: float = 30.0
    claude_max_retries: int = 2

    dead_letter_path: str = "ai_layer_dead_letter.jsonl"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

## 3. `ai_layer/schemas.py`

Defines: `AlertIn`/`Alert` (mirrors `app.schemas`), `Profile` (mirrors
`app.models.Profile`, **with a `route_id` validator** — see below), `ActionTemplate`,
`PredictionRecord` (`segment_name`, `risk_level`, `flood_prediction_id: Optional[int]`,
`window_start`/`window_end: Optional[datetime]` — matching the extended
`/alerts/predict` response from §1a), the tagged union `TemplateMatch | PredictionMatch | NoMatch`
(`SelectionResult`), `MessageIn`/`Message`, `FeedbackCategory` (str enum, the 6 fixed
categories), `FeedbackClassification` (Claude's structured-output target: `category` +
`confidence: float = Field(ge=0, le=1)`), `FeedbackIn`/`Feedback`.

**`route_id` constraint** (formal, documented since ai_layer has no DB access to
really check it): `profiles.route_id` stores a `road_segments.segment_name` value
directly (e.g. `"Adams_Arcade"`), matching the `segment` string from
`/alerts/predict`. A `field_validator` enforces it's non-empty and matches
`^[A-Za-z0-9_]+$` (the naming convention actually used by seeded segments) — this is
structural validation only; it cannot confirm the value matches a currently-seeded
segment (that's only knowable by calling the live API, which `template_selector` does).

**Language handling**: `Profile.language` defaults to `"en"` like the DB column, but
is always threaded through explicitly — `select_content` → `match_templates(...,
language=profile.language)` — never hardcoded past the one default that already
exists server-side.

## 4. `ai_layer/clients/profiles_repo.py`

```python
from abc import ABC, abstractmethod
from ..schemas import Profile

class ProfileNotFoundError(Exception):
    def __init__(self, profile_id: int):
        super().__init__(f"profile {profile_id} not found")
        self.profile_id = profile_id

class ProfilesRepo(ABC):
    """Abstract contract. A future ApiProfilesRepo (once profiles.py is wired up)
    implements this same interface calling GET /profiles/{id} and GET /profiles —
    callers (template_selector, personalizer, main.py) never need to change."""
    @abstractmethod
    async def get_profile(self, profile_id: int) -> Profile: ...
    @abstractmethod
    async def list_profiles(self) -> list[Profile]: ...

DEFAULT_MOCK_PROFILES: list[Profile] = [
    # rural/ward track, all pinned to ward="Kisumu_Central" to match seeded test alert id 1 (65mm, high)
    Profile(id=1, phone_number="+254712345001", channel="whatsapp", language="en",
            user_type="rural", occupation="farmer", ward="Kisumu_Central", key_asset="maize_farm"),
    Profile(id=2, phone_number="+254712345002", channel="sms", language="en",
            user_type="rural", occupation="fisherman", ward="Kisumu_Central", key_asset="fishing_boat"),
    Profile(id=3, phone_number="+254712345003", channel="whatsapp", language="sw",
            user_type="rural", occupation="farmer", ward="Kisumu_Central", key_asset="maize_farm"),
    # urban/corridor track, route_id values matching 3 of the 7 seeded Ngong_Road segments,
    # to match seeded test alert id 2 (Ngong_Road, 40mm, medium)
    Profile(id=4, phone_number="+254712345004", channel="whatsapp", language="en",
            user_type="urban", occupation="driver", route_id="Adams_Arcade", key_asset="matatu_route_46"),
    Profile(id=5, phone_number="+254712345005", channel="sms", language="en",
            user_type="urban", occupation="driver", route_id="Dagoretti_Corner", key_asset="motorbike"),
    Profile(id=6, phone_number="+254712345006", channel="whatsapp", language="sw",
            user_type="urban", occupation="driver", route_id="Kilimani_Junction", key_asset="delivery_van"),
]

class MockProfilesRepo(ProfilesRepo):
    def __init__(self, profiles: list[Profile] | None = None):
        self._profiles = {p.id: p for p in (profiles or DEFAULT_MOCK_PROFILES)}
    async def get_profile(self, profile_id: int) -> Profile:
        try:
            return self._profiles[profile_id]
        except KeyError:
            raise ProfileNotFoundError(profile_id)
    async def list_profiles(self) -> list[Profile]:
        return list(self._profiles.values())
```

Rationale: profiles 1–2 hit real seeded templates (`heavy_rainfall`×farmer/fisherman×
high×en). Profile 3 duplicates farmer but `language="sw"` — since only `en` templates
are seeded, this is a deliberate `NoMatch` case exercising language as a first-class
parameter end-to-end. Profiles 4–5 hit real flagged segments at 40mm rainfall
(`Adams_Arcade` cap 20, `Dagoretti_Corner` cap 30 — both flagged); profile 6
(`Kilimani_Junction`, cap 40) is *not* flagged at exactly 40mm rainfall (flagging
requires `rainfall_mm > capacity`), giving a second incidental `NoMatch` case on the
urban track too.

## 5. `ai_layer/clients/alerts_api.py`

Async `httpx.AsyncClient`-based client covering every Tahadhari endpoint ai_layer
touches: `/alerts/ingest`, `/alerts/{id}`, `/alerts/predict/{id}`, `/templates/match`,
`/messages/`, `/feedback/`.

Typed exception hierarchy: `AlertsApiError` (base) → `AlertsApiConnectionError`,
`AlertsApiTimeoutError`, `AlertsApiServerError` (5xx, **retryable**),
`AlertsApiClientError` (4xx, **not retried** — fails fast/loud), with
`AlertsApiNotFoundError(AlertsApiClientError)` for 404 specifically.

Retry via `tenacity.AsyncRetrying`: only `AlertsApiConnectionError` /
`AlertsApiTimeoutError` / `AlertsApiServerError` are retried, up to
`tahadhari_api_max_retries` (default 3) additional attempts, exponential backoff
(`wait_exponential(multiplier=0.5, min=0.5, max=8)`), then reraise. Every request is
`logger.debug`-logged before (method/path/params/json) and after (status code).

Typed methods: `ingest_alert(AlertIn) -> Alert`, `get_alert(alert_id) -> Alert`,
`predict_flooding(alert_id) -> list[PredictionRecord]` (parses the extended response
from §1a: `flood_prediction_id=p.get("flood_prediction_id")`,
`window_start=p.get("window_start")`, `window_end=p.get("window_end")`, alongside
`segment`/`risk` — using `.get()` defensively so the client still degrades gracefully
if it's ever pointed at an unpatched/older API instance), `match_templates(*,
hazard_type, occupation, severity, language="en") -> list[ActionTemplate]`,
`create_message(MessageIn) -> Message`, `create_feedback(FeedbackIn) -> Feedback`.

Note in `get_alert`: since `alerts.py` has no `HTTPException` handling (existing,
out-of-scope bug), a bad `alert_id` may 200 with a malformed body instead of 404 —
`get_alert` catches the resulting Pydantic validation error and re-raises a clear
`AlertsApiError` rather than propagating a confusing raw exception.

## 6. `ai_layer/clients/claude_client.py`

Wraps `anthropic.AsyncAnthropic` (model from `Settings.anthropic_model`, i.e.
`claude-sonnet-5`). **Does not reimplement retry/backoff** — the Anthropic SDK's own
client already auto-retries connection errors/408/409/429/5xx with exponential
backoff via `max_retries`, and enforces `timeout` as a hard per-request ceiling;
per the skill's own guidance, custom retry logic is only worth adding when it's
needed beyond what the SDK provides, which it isn't here.

Two methods:
- `create_text(*, system, user_content, max_tokens=1024) -> str` — plain
  `messages.create()`, concatenates text blocks, used for the grammar/phrasing pass.
- `parse_structured(*, system, user_content, output_model: Type[T], max_tokens=1024)
  -> T` — uses `client.messages.parse(..., output_format=output_model)` (per the
  Claude API skill's structured-outputs guidance), returns `response.parsed_output`.
  Used for the urban-track flood-warning draft and the feedback classifier.

Typed exceptions: `ClaudeClientError` (base) → `ClaudeTimeoutError`,
`ClaudeAPIError(status_code, message)`, `ClaudeParsingError`. Catches
`anthropic.APITimeoutError` / `APIStatusError` / `APIConnectionError` /
`pydantic.ValidationError` and re-raises as the typed equivalents.

**Verify before relying on it**: confirm `AsyncAnthropic().messages.parse` exists on
the installed SDK version (`python -c "import anthropic; print(anthropic.AsyncAnthropic().messages.parse)"`).
If it doesn't, fall back to `output_config={"format": {"type": "json_schema", "schema":
output_model.model_json_schema()}}` on `messages.create()` plus
`output_model.model_validate_json(text)`.

## 7. `ai_layer/dead_letter.py`

Shared by both services (an addition beyond the literal file skeleton — needed since
the brief asks for identical dead-letter handling in both Task 2 and Task 3). A plain
JSONL file at `Settings.dead_letter_path`:

```python
def write_dead_letter(record_type: str, payload: dict) -> None:
    """record_type: 'message' | 'feedback'. Appends one JSON line
    {"record_type", "payload", "failed_at"} so nothing is silently lost if
    /messages or /feedback is briefly unreachable. No automated replay tool —
    lines are meant to be read and replayed manually (out of scope per the brief:
    'keep it simple')."""
```

Guarded by a `threading.Lock` for concurrent-append safety. Considered SQLite;
rejected as unnecessary for what the brief explicitly calls a "simple" fallback.

## 8. `ai_layer/services/template_selector.py`

```python
async def select_content(alert: Alert, profile: Profile, *,
                          client: AlertsApiClient | None = None) -> SelectionResult:
```

Branches on `alert.geography_type`:
- `"ward"` → requires `profile.occupation`; calls `client.match_templates(hazard_type=
  alert.hazard_type, occupation=profile.occupation, severity=alert.severity,
  language=profile.language)`. Empty list → `NoMatch` (`logger.warning`, not silent).
  Non-empty → `TemplateMatch(alert, profile, template=templates[0])`.
- `"corridor"` → requires `profile.route_id`; calls `client.predict_flooding(alert.id)`,
  looks for a `PredictionRecord.segment_name == profile.route_id`. Found →
  `PredictionMatch(..., window_start=pred.window_start, window_end=pred.window_end,
  flood_prediction_id=pred.flood_prediction_id)` — real values now that §1a extends
  the endpoint to return them. Not found → `NoMatch`.
- Anything else → `NoMatch` with a reason string.

`AlertsApiError` (network failure, retries exhausted, unexpected 4xx) is **not**
caught here — it propagates. Only "call succeeded, zero matching rows" becomes a
`NoMatch`; a real API failure is not silently treated as "no content."

## 9. `ai_layer/services/personalizer.py`

- `build_placeholder_values(alert, profile) -> dict[str, str]` — maps `rainfall_mm`,
  `ward`/`corridor` (depending on `geography_type`), `occupation`, `key_asset`,
  `route_id` to real values, only including a key when the source data is actually
  present.
- `fill_placeholders(template_text, values) -> str` — pre-check: every `{word}` token
  found via `\{(\w+)\}` must have an entry in `values`, else raises
  `MissingPlaceholderValueError(placeholder_name)`. Substitutes, then **defensively
  re-scans** the result with a broader `\{[^{}]*\}` pattern for *any* remaining brace
  pair (catches malformed tokens like `{when?}` the strict pre-check regex wouldn't
  even recognize) — raises `LeftoverPlaceholderError` if anything remains. A leftover
  placeholder is a hard failure, never sent.
- Grammar pass (`TemplateMatch` path): strict system prompt forbidding any change to
  facts/instructions, output-only-corrected-text. On `ClaudeClientError` (after SDK
  retries) or an empty response, **falls back to the unedited filled template text**
  and logs at `ERROR` ("FALLING BACK to unedited template text") — visible, not silent.
- Flood-warning generation (`PredictionMatch` path): `parse_structured` against a
  `FloodWarningDraft(message_text: str)` schema, strict prompt requiring segment name +
  risk level (+ window if present) and no invented data. On any parse/API failure,
  falls back to `_plain_flood_sentence(content)` — a deterministic sentence built
  directly from `segment_name`/`risk_level`/window fields, so a malformed LLM response
  never blocks a time-sensitive flood warning.
- `personalize_message(alert, profile, content, *, claude_client=None,
  alerts_api_client=None) -> Message` — dispatches on `isinstance(content, ...)`,
  builds `MessageIn`, then POSTs via `client.create_message(...)`. On
  `AlertsApiError`, writes a dead-letter record (`write_dead_letter("message", ...)`),
  logs `ERROR` with enough context to retry manually, and raises
  `MessageDeliveryError` — data is preserved on disk even though the call itself
  ultimately surfaces as a failure to the caller.

## 10. `ai_layer/services/feedback_classifier.py`

```python
async def classify_feedback(message: Message, reply_text: str, *,
                             claude_client=None, alerts_api_client=None) -> Feedback:
```

Calls `claude_client.parse_structured(..., output_model=FeedbackClassification)` with
a system prompt naming the 6 fixed categories and requiring a confidence score. On
`ClaudeClientError`/`ValidationError`, retries **once** with the same prompt plus a
stricter reminder appended. If that also fails, falls back to `category=OTHER,
confidence=0.0` (logged at `ERROR`) — `classify_feedback` itself never raises on a
classification failure; the only way it raises is if the subsequent `POST /feedback/`
fails, in which case (same as the personalizer) a dead-letter record is written first
and `FeedbackClassificationError` is raised — data is never silently lost.

## 11. `ai_layer/main.py`

End-to-end example: for each of two scenarios (rural/ward alert + farmer profile;
urban/corridor alert + driver profile with a matching `route_id`) — `ingest_alert` →
`select_content` → `personalize_message` → log the created message → simulate a
WhatsApp reply string → `classify_feedback` → log the result. Uses `MockProfilesRepo`
directly (no swap needed for this demo). Requires `uvicorn app.main:app --reload`
running and a real `ANTHROPIC_API_KEY` (falls back gracefully, per the personalizer's
design, if the key is missing/invalid — the pipeline still completes using unedited
template text instead of crashing).

## 12. Tests (`ai_layer/tests/`)

`conftest.py`: shared fixtures — `sample_alert_ward`, `sample_profile_farmer`,
`sample_profile_farmer_sw`, `sample_template`.

- **`test_placeholder_filling.py`**: happy path (no `{...}` left, real values
  substituted); `MissingPlaceholderValueError` when a template references a key not in
  `values`; `LeftoverPlaceholderError` specifically via a malformed token like
  `{when?}` that the strict pre-check regex doesn't recognize — proving the
  post-substitution safety net (not just the pre-check) is what catches it.
- **`test_template_selector.py`**: no-match path (mock `match_templates` →
  `[]`, using the `sw`-language farmer fixture, asserting `NoMatch` + a WARNING log via
  `caplog`); a happy-path match for coverage; a corridor no-match path (predicted
  segments don't include the profile's `route_id`).
- **`test_feedback_classifier.py`**: happy path (mocked `parse_structured` returns a
  valid `FeedbackClassification`, mocked `create_feedback` returns a `Feedback` with an
  id); malformed-JSON-then-fallback path (`parse_structured` raises on **both** calls,
  asserting the final persisted `feedback_type == OTHER` and an ERROR log was emitted).

All Claude and Alerts-API calls are mocked at the `clients/` boundary
(`unittest.mock.AsyncMock`) — no real network/DB access in any test. Add a root
`pytest.ini` with `asyncio_mode = auto` so async tests don't need individual
`@pytest.mark.asyncio` decorators.

## 13. `requirements.txt` — additions (careful: file is UTF-16-LE with CRLF)

Add: `anthropic`, `pydantic-settings`, `httpx`, `tenacity`, `pytest`, `pytest-asyncio`,
`pytest-mock`. **Must preserve the UTF-16 encoding** or it produces an unrelated
encoding-only diff across the whole file:

```python
with open("requirements.txt", "rb") as f:
    text = f.read().decode("utf-16")   # "utf-16" (not "-le") auto-detects/strips the BOM
if not text.endswith("\r\n"):
    text += "\r\n"
text += "\r\n".join(["anthropic", "pydantic-settings", "httpx", "tenacity",
                      "pytest", "pytest-asyncio", "pytest-mock"]) + "\r\n"
with open("requirements.txt", "wb") as f:
    f.write(text.encode("utf-16"))     # re-adds a correct BOM
```

After `pip install -r requirements.txt`, replace the bare names with
`name==<installed version>` (via `pip freeze | grep -iE "anthropic|pydantic-settings|httpx|tenacity|pytest"`)
to match the file's existing fully-pinned style, then redo the encode step.

## 14. `.env.example` (new, repo root — `.env` itself stays gitignored)

```
DATABASE_URL=postgresql://user:pass@localhost:5432/tahadhari

ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5

TAHADHARI_API_BASE_URL=http://localhost:8000
TAHADHARI_API_TIMEOUT_SECONDS=5.0
TAHADHARI_API_MAX_RETRIES=3

CLAUDE_TIMEOUT_SECONDS=30.0
CLAUDE_MAX_RETRIES=2

DEAD_LETTER_PATH=ai_layer_dead_letter.jsonl
```

## 15. `seed_profiles.py` (new, repo root, sibling to `seed_segments.py`)

Beyond the literal file list, but necessary: `MockProfilesRepo`'s profiles only exist
in-memory, while `POST /messages/`'s FK check needs matching rows in the real
`profiles` table to avoid 404s during the `main.py` end-to-end demo. Follows
`seed_segments.py`'s exact pattern (`SessionLocal`, insert, commit, print count),
inserting the same 6 profiles from `DEFAULT_MOCK_PROFILES`. **Caveat to note inline**:
Postgres auto-assigns primary keys, so ids only line up with the hardcoded 1–6 if run
against a freshly created, empty `profiles` table — same "run once against a fresh DB"
caveat `seed_segments.py` already carries.

## Order of implementation

1. `requirements.txt` + `.env.example` + `pytest.ini`.
2. `app/routers/alerts.py` (§1a: extend `predict_flooding`'s response) +
   `API_GUIDE.md` update — smoke-test `POST /alerts/predict/2` directly (existing
   seeded alert) and confirm the response now includes `flood_prediction_id`/
   `window_start`/`window_end` before building anything on top of it.
3. `ai_layer/config.py` → `ai_layer/schemas.py`.
4. `app/schemas.py` additions, then `app/routers/messages.py` /
   `app/routers/feedback.py` / `app/main.py` registration — smoke-test via `/docs`
   before writing any client code that depends on them.
5. `ai_layer/clients/profiles_repo.py` (mock data).
6. `ai_layer/clients/alerts_api.py` — smoke-test against the now-running API.
7. `ai_layer/clients/claude_client.py` — smoke-test independently with a real key.
8. `ai_layer/dead_letter.py`.
9. `services/template_selector.py` + `tests/conftest.py` +
   `tests/test_template_selector.py`.
10. `services/personalizer.py` + `tests/test_placeholder_filling.py`.
11. `services/feedback_classifier.py` + `tests/test_feedback_classifier.py`.
12. `ai_layer/main.py`.
13. `seed_profiles.py`, then full `pytest` run.

Commit incrementally along these boundaries using Conventional Commits (`feat(api):
add /messages and /feedback endpoints`, `feat(ai_layer): add template selector`,
`test(ai_layer): ...`, etc.) on the new branch off `main`. **No commit trailers.**

## Verification

1. **Start the API**: `uvicorn app.main:app --reload` → `/docs` should now list
   `messages` and `feedback` tags with `POST /messages/`, `GET /messages/{id}`,
   `POST /feedback/`, `GET /feedback/{id}`.
2. **Predict endpoint extension**: `curl -X POST http://localhost:8000/alerts/predict/2`
   (seeded alert id 2, Ngong_Road, 40mm) — each object in `predictions` should now
   include `flood_prediction_id`, `window_start`, `window_end` alongside the existing
   `segment`/`risk` keys.
3. **Manual smoke test** (after `seed_profiles.py`):
   ```bash
   curl -X POST http://localhost:8000/messages/ -H "Content-Type: application/json" \
     -d '{"profile_id":1,"alert_id":1,"final_text":"test","channel":"whatsapp"}'
   # expect 201, delivery_status="pending"
   curl http://localhost:8000/messages/1                     # expect 200
   curl -X POST http://localhost:8000/messages/ -H "Content-Type: application/json" \
     -d '{"profile_id":9999,"alert_id":1,"final_text":"x","channel":"sms"}'
   # expect 404 "Profile 9999 not found"
   ```
4. **End-to-end run**: `python -m ai_layer.main` — DEBUG logs should show calls to
   `/templates/match` and `/alerts/predict/{id}`, two "Created message id=..." lines
   with real (non-placeholder) text, two "Classified feedback id=..." lines. Pulling
   `ANTHROPIC_API_KEY` should degrade gracefully (fallback-to-template-text ERROR log,
   pipeline still completes) rather than crash — that's the designed fallback, not a
   bug.
5. **Unit tests**: `pytest ai_layer/tests -v` — all pass with `ANTHROPIC_API_KEY`
   unset and no API server running at all (proves the `clients/` boundary is fully
   mocked, no real network/DB access anywhere in the suite).
