from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from ..auth import require_service_or_admin
from ..database import commit_or_error, get_db
from ..models import Profile, RegistrationRequest
from ..schemas import LocationUpdateIn, ProfileIn, ProfileOut

router = APIRouter(dependencies=[Depends(require_service_or_admin)])


@router.post("/", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileIn, db: Session = Depends(get_db)):
    db_profile = Profile(
        phone_number=payload.phone_number,
        channel=payload.channel.value,
        language=payload.language,
        user_type=payload.user_type.value,
        occupation=payload.occupation,
        ward=payload.ward,
        route_id=payload.route_id,
        key_asset=payload.key_asset,
        registration_source=payload.registration_source.value,
        registered_by=payload.registered_by,
    )
    commit_or_error(
        db, db_profile, resource_name="profile",
        integrity_conflict_detail=f"Profile with phone_number {payload.phone_number!r} already exists",
    )

    # Resolve any pending registration-webhook intent for this phone number now that
    # a profile actually exists for it (see app/routers/registration.py).
    db.query(RegistrationRequest).filter(
        RegistrationRequest.phone_number == payload.phone_number,
        RegistrationRequest.resolved_at.is_(None),
    ).update({"resolved_at": func.now(), "profile_id": db_profile.id})
    db.commit()

    return db_profile


@router.patch("/{profile_id}/location", response_model=ProfileOut)
def update_profile_location(profile_id: int, payload: LocationUpdateIn, db: Session = Depends(get_db)):
    """Persists a geocoded location onto a profile -- called by ai_layer's
    location-weather poller after a successful GoogleMapsClient.geocode() (see
    ai_layer/services/location_weather.py). Does not touch registration_requests;
    request-state advancement is a separate call to
    PATCH /registration/requests/{id}/state."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    profile.resolved_lat = payload.lat
    profile.resolved_lon = payload.lon
    profile.resolved_place_name = payload.place_name
    commit_or_error(db, profile, resource_name="profile")
    return profile


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return profile


@router.get("/", response_model=list[ProfileOut])
def list_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(Profile).order_by(Profile.id).offset(skip).limit(limit).all()
