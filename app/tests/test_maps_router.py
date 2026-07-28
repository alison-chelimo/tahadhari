from datetime import datetime, timedelta

from app.auth import SERVICE_API_KEY
from app.models import Alert, FloodPrediction, RoadSegment

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def _make_corridor_alert(db_session) -> Alert:
    alert = Alert(
        hazard_type="heavy_rainfall",
        severity="high",
        geography_type="corridor",
        geography_ref="Ngong_Road",
        rainfall_mm=70.0,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def test_get_corridor_maps_success(client, db_session):
    alert = _make_corridor_alert(db_session)
    segment = RoadSegment(
        corridor_name="Ngong_Road",
        segment_name="Adams_Arcade",
        start_lat=-1.3003356,
        start_lon=36.7739845,
        end_lat=-1.3001697,
        end_lon=36.7768293,
        drainage_capacity_mm=20.0,
    )
    db_session.add(segment)
    db_session.commit()
    db_session.refresh(segment)

    prediction = FloodPrediction(
        alert_id=alert.id,
        segment_id=segment.id,
        risk_level="high",
        window_start=datetime.utcnow(),
        window_end=datetime.utcnow() + timedelta(hours=3),
    )
    db_session.add(prediction)
    db_session.commit()

    response = client.get(f"/maps/alerts/{alert.id}/corridor", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["alert_id"] == alert.id
    assert body["corridor_name"] == "Ngong_Road"
    assert len(body["maps"]) == 1
    assert "staticmap.openstreetmap.de" in body["maps"][0]["map_url"]


def test_get_corridor_maps_non_corridor_alert_400(client, db_session):
    alert = Alert(
        hazard_type="heavy_rainfall",
        severity="high",
        geography_type="ward",
        geography_ref="Kisumu_Central",
        rainfall_mm=65.0,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    response = client.get(f"/maps/alerts/{alert.id}/corridor", headers=AUTH_HEADERS)
    assert response.status_code == 400


def test_get_corridor_maps_alert_not_found_404(client):
    response = client.get("/maps/alerts/999/corridor", headers=AUTH_HEADERS)
    assert response.status_code == 404
