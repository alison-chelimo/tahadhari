from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from ..auth import require_service_or_admin
from ..database import get_db
from ..models import Profile
from ..schemas import ProfileIn, ProfileOut

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
    try:
        db.add(db_profile)
        db.commit()
        db.refresh(db_profile)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile with phone_number {payload.phone_number!r} already exists",
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist profile")
    return db_profile


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return profile


@router.get("/", response_model=list[ProfileOut])
def list_profiles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Profile).offset(skip).limit(limit).all()
