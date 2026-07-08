# Climate Risk Advisor — Backend API Guide

Base URL (local): `http://localhost:8000`
Base URL (deployed): _to be added once Railway deployment is live_

Interactive docs available at `/docs` on either URL.

---

## 1. Ingest an alert

Classifies severity automatically based on rainfall, and stores the alert.

**Endpoint:** `POST /alerts/ingest`

**Request body:**
```json
{
  "source": "KMD_test",
  "geography_type": "ward",
  "geography_ref": "Kisumu_Central",
  "rainfall_mm": 65,
  "raw_payload": {"forecast_window": "next_24h", "confidence": "high"}
}
```

**Notes on fields:**
- `geography_type`: either `"ward"` (rural/occupation track) or `"corridor"` (urban track)
- `geography_ref`: the ward name (e.g. `"Kisumu_Central"`) or corridor name (e.g. `"Ngong_Road"`) — must match exactly what's seeded in `road_segments.corridor_name` for the urban track to work
- `raw_payload`: free-form JSON, not validated — store whatever the source feed gives you

**Response:**
```json
{
  "id": 1,
  "hazard_type": "heavy_rainfall",
  "severity": "high",
  "geography_type": "ward",
  "geography_ref": "Kisumu_Central",
  "rainfall_mm": 65,
  "created_at": "2026-07-07T13:30:12.284924Z"
}
```

**Severity classification logic:**
- `rainfall_mm >= 60` → `"high"`
- `rainfall_mm >= 30` → `"medium"`
- otherwise → `"low"`

**Python example:**
```python
import requests

response = requests.post("http://localhost:8000/alerts/ingest", json={
    "source": "KMD_test",
    "geography_type": "ward",
    "geography_ref": "Kisumu_Central",
    "rainfall_mm": 65,
    "raw_payload": {"forecast_window": "next_24h", "confidence": "high"}
})
alert = response.json()
print(alert["id"], alert["severity"])
```

---

## 2. Get a matching action template

Looks up the vetted, pre-written template for a given hazard/occupation/severity/language combination.

**Endpoint:** `GET /templates/match`

**Query parameters:**
| Param | Required | Example |
|---|---|---|
| `hazard_type` | yes | `heavy_rainfall` |
| `occupation` | yes | `farmer` |
| `severity` | yes | `high` |
| `language` | no (defaults to `en`) | `en` |

**Response:**
```json
[
  {
    "id": 1,
    "hazard_type": "heavy_rainfall",
    "occupation": "farmer",
    "severity": "high",
    "language": "en",
    "template_text": "Heavy rainfall expected in {ward} within 24 hours. Delay planting by 48 hours and cover stored seed before rainfall begins."
  }
]
```

**Important — placeholder convention:** `template_text` contains `{placeholder}` tokens that must be filled in before sending to a user. Placeholder names match source column names exactly:

| Placeholder | Source |
|---|---|
| `{ward}` | `alerts.geography_ref` (when `geography_type` = `"ward"`) |
| `{corridor}` | `alerts.geography_ref` (when `geography_type` = `"corridor"`) |
| `{rainfall_mm}` | `alerts.rainfall_mm` |
| `{segment_name}` | `road_segments.segment_name` |
| `{window_start}` / `{window_end}` | `flood_predictions.window_start` / `window_end` |
| `{risk_level}` | `flood_predictions.risk_level` |
| `{occupation}` | `profiles.occupation` |
| `{key_asset}` | `profiles.key_asset` |
| `{route_id}` | `profiles.route_id` |

Templates are **pre-written per language, not live-translated** — the personalization layer's job is to select the correct template and fill in placeholders, not generate or translate free text.

**Python example:**
```python
import requests

response = requests.get("http://localhost:8000/templates/match", params={
    "hazard_type": "heavy_rainfall",
    "occupation": "farmer",
    "severity": "high",
    "language": "en"
})
templates = response.json()
print(templates[0]["template_text"])
```

---

## 3. Get flood predictions for an alert

Runs the rainfall/drainage threshold check for a corridor alert and returns flagged road segments.

**Endpoint:** `POST /alerts/predict/{alert_id}`

**Path parameter:** `alert_id` — must be the id of an alert where `geography_type` is `"corridor"` and `geography_ref` matches a seeded `road_segments.corridor_name` (currently only `"Ngong_Road"` is seeded).

**Response:**
```json
{
  "flagged_segments": 6,
  "predictions": [
    {"flood_prediction_id": 1, "segment": "Dagoretti_Corner", "risk": "medium", "window_start": "2026-07-07T13:30:12.284924Z", "window_end": "2026-07-07T16:30:12.284924Z"},
    {"flood_prediction_id": 2, "segment": "Riara_Road_Junction", "risk": "high", "window_start": "2026-07-07T13:30:12.284924Z", "window_end": "2026-07-07T16:30:12.284924Z"},
    {"flood_prediction_id": 3, "segment": "Adams_Arcade", "risk": "high", "window_start": "2026-07-07T13:30:12.284924Z", "window_end": "2026-07-07T16:30:12.284924Z"},
    {"flood_prediction_id": 4, "segment": "Jamhuri_Junction", "risk": "medium", "window_start": "2026-07-07T13:30:12.284924Z", "window_end": "2026-07-07T16:30:12.284924Z"},
    {"flood_prediction_id": 5, "segment": "Yaya_Centre", "risk": "medium", "window_start": "2026-07-07T13:30:12.284924Z", "window_end": "2026-07-07T16:30:12.284924Z"},
    {"flood_prediction_id": 6, "segment": "Kindaruma_Road_Junction", "risk": "high", "window_start": "2026-07-07T13:30:12.284924Z", "window_end": "2026-07-07T16:30:12.284924Z"}
  ]
}
```

`flood_prediction_id`/`window_start`/`window_end` come directly from the created
`flood_predictions` row for each flagged segment (a fixed 3-hour window starting at
the time the prediction was computed).

**Threshold logic:**
- A segment is flagged if `alert.rainfall_mm > segment.drainage_capacity_mm`
- Flagged as `"high"` if `rainfall_mm > drainage_capacity_mm * 1.5`, otherwise `"medium"`

**Python example:**
```python
import requests

response = requests.post("http://localhost:8000/alerts/predict/2")
predictions = response.json()
print(predictions["flagged_segments"], "segments flagged")
```

---

## Schema reference (for context)

| Table | Key columns |
|---|---|
| `alerts` | id, hazard_type, severity, geography_type, geography_ref, rainfall_mm, source, raw_payload, created_at |
| `profiles` | id, phone_number, channel, language, user_type, occupation, ward, route_id, key_asset |
| `action_templates` | id, hazard_type, occupation, severity, language, template_text |
| `road_segments` | id, corridor_name, segment_name, start/end lat/lon, drainage_capacity_mm |
| `flood_predictions` | id, alert_id, segment_id, risk_level, window_start, window_end |
| `messages` | id, profile_id, alert_id, template_id, flood_prediction_id, final_text, channel, delivery_status, sent_at |
| `feedback` | id, message_id, profile_id, feedback_type, feedback_text, created_at |

---

## Currently seeded test data

**Action templates (6):** heavy_rainfall × {farmer, fisherman, driver} × {high, medium}, language `en`

**Road segments (7), corridor `Ngong_Road`:**
| Segment | Drainage capacity (mm) |
|---|---|
| Dagoretti_Corner | 30 |
| Riara_Road_Junction | 25 |
| Adams_Arcade | 20 |
| Jamhuri_Junction | 35 |
| Kilimani_Junction | 40 |
| Yaya_Centre | 28 |
| Kindaruma_Road_Junction | 22 |

**Test alerts:** alert `id: 1` (Kisumu_Central, 65mm, severity high), alert `id: 2` (Ngong_Road, 40mm, severity medium)

---

## Known limitations (MVP scope)

- Only one hazard type (`heavy_rainfall`) is supported
- Only one urban corridor (`Ngong_Road`) has seeded road segments
- `messages` and `feedback` tables exist in the schema but have no endpoints built yet — flag to Person One if you need to write to them before endpoints exist
- No authentication on any endpoint — local/demo use only