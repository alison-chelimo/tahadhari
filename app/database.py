from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import os
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def commit_or_error(db: Session, obj, *, resource_name: str, integrity_conflict_detail: str | None = None):
    """Add+commit+refresh `obj`, translating DB failures into HTTPExceptions.

    `integrity_conflict_detail` opts a caller into treating IntegrityError as a 409
    (e.g. a unique-constraint violation); callers that don't pass it keep IntegrityError
    falling through to the same 500 as any other SQLAlchemyError, matching this
    project's pre-existing per-router behavior.
    """
    try:
        db.add(obj)
        db.commit()
        db.refresh(obj)
    except IntegrityError:
        db.rollback()
        if integrity_conflict_detail is not None:
            raise HTTPException(status_code=409, detail=integrity_conflict_detail)
        raise HTTPException(status_code=500, detail=f"Failed to persist {resource_name}")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to persist {resource_name}")
    return obj