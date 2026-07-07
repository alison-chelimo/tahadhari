from app.database import SessionLocal
from app.models import RoadSegment

db = SessionLocal()

segments = [
    {"corridor_name": "Ngong_Road", "segment_name": "Dagoretti_Corner", "start_lat": -1.2994960, "start_lon": 36.7638549, "end_lat": -1.3000253, "end_lon": 36.7662580, "drainage_capacity_mm": 30},
    {"corridor_name": "Ngong_Road", "segment_name": "Riara_Road_Junction", "start_lat": -1.3000596, "start_lon": 36.7662580, "end_lat": -1.3002502, "end_lon": 36.7728829, "drainage_capacity_mm": 25},
    {"corridor_name": "Ngong_Road", "segment_name": "Adams_Arcade", "start_lat": -1.3003356, "start_lon": 36.7739845, "end_lat": -1.3001697, "end_lon": 36.7768293, "drainage_capacity_mm": 20},
    {"corridor_name": "Ngong_Road", "segment_name": "Jamhuri_Junction", "start_lat": -1.3001697, "start_lon": 36.7768293, "end_lat": -1.3000953, "end_lon": 36.7792641, "drainage_capacity_mm": 35},
    {"corridor_name": "Ngong_Road", "segment_name": "Kilimani_Junction", "start_lat": -1.2999250, "start_lon": 36.7796765, "end_lat": -1.2997802, "end_lon": 36.7827234, "drainage_capacity_mm": 40},
    {"corridor_name": "Ngong_Road", "segment_name": "Yaya_Centre", "start_lat": -1.2997626, "start_lon": 36.7853637, "end_lat": -1.2997524, "end_lon": 36.7866159, "drainage_capacity_mm": 28},
    {"corridor_name": "Ngong_Road", "segment_name": "Kindaruma_Road_Junction", "start_lat": -1.2995661, "start_lon": 36.7882356, "end_lat": -1.2993951, "end_lon": 36.7920129, "drainage_capacity_mm": 22},
]

for s in segments:
    db.add(RoadSegment(**s))

db.commit()
print(f"Seeded {len(segments)} road segments.")