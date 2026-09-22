from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.db import get_session
from app.models.user import User

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.get("/")
def get_users(session: Session = Depends(get_session)):
    return session.exec(select(User)).all()