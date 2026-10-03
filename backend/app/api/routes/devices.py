from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import app.core.security as acs
from app.core.db import get_session
from app.models.user import User
from app.schemas.user import LoginRequest

router = APIRouter(
    prefix="/",
    tags=["devices"],
)

@router.post("/ws/telemetry")
def get_users(session: Session = Depends(get_session)):
    return session.exec().all()
