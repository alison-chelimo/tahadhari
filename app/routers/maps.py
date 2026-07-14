from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert, FloodPrediction, RoadSegment
from ..schemas import CorridorMapsOut, CorridorSegmentMapOut
from ..services.maps import build_segment_map_url

router = APIRouter()


@router.get("/alerts/{alert_id}/corridor", response_model=CorridorMapsOut)
def get_corridor_maps(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    if alert.geography_type != "corridor":
        raise HTTPException(status_code=400, detail="Map rendering is available only for corridor alerts")

    predictions = db.query(FloodPrediction).filter(FloodPrediction.alert_id == alert.id).all()
    maps: list[CorridorSegmentMapOut] = []

    for prediction in predictions:
        segment = db.query(RoadSegment).filter(RoadSegment.id == prediction.segment_id).first()
        if not segment:
            continue
        if None in (segment.start_lat, segment.start_lon, segment.end_lat, segment.end_lon):
            continue

        maps.append(
            CorridorSegmentMapOut(
                flood_prediction_id=prediction.id,
                segment_name=segment.segment_name,
                risk_level=prediction.risk_level,
                window_start=prediction.window_start,
                window_end=prediction.window_end,
                map_url=build_segment_map_url(
                    start_lat=segment.start_lat,
                    start_lon=segment.start_lon,
                    end_lat=segment.end_lat,
                    end_lon=segment.end_lon,
                ),
            )
        )

    return CorridorMapsOut(alert_id=alert.id, corridor_name=alert.geography_ref, maps=maps)
