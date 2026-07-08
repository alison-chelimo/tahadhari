from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import create_access_token, verify_password
from ..database import get_db
from ..models import AdminUser
from ..schemas import LoginIn, TokenOut

router = APIRouter()


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    admin = db.query(AdminUser).filter(AdminUser.username == payload.username).first()
    if not admin or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return TokenOut(access_token=create_access_token(admin.username))
