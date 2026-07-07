from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Alert, RoadSegment, FloodPrediction
from ..schemas import AlertIn, AlertOut
from datetime import datetime, timedelta

router = APIRouter()

def classify_severity(rainfall_mm: float) -> str:
    if rainfall_mm >= 60:
        return "high"
    elif rainfall_mm >= 30:
        return "medium"
    return "low"

@router.post("/ingest", response_model=AlertOut)
def ingest_alert(alert: AlertIn, db: Session = Depends(get_db)):
    severity = classify_severity(alert.rainfall_mm)
    db_alert = Alert(
        hazard_type="heavy_rainfall",
        severity=severity,
        geography_type=alert.geography_type,
        geography_ref=alert.geography_ref,
        rainfall_mm=alert.rainfall_mm,
        source=alert.source,
        raw_payload=alert.raw_payload,
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    return db.query(Alert).filter(Alert.id == alert_id).first()

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
            {"segment": seg.segment_name, "risk": p.risk_level}
            for seg, p in zip(flagged_segments, predictions)
        ]
    }