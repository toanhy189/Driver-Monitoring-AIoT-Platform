from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import app.core.security as acs
from app.core.db import get_session
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, UserResponse

router = APIRouter(
    prefix="",
    tags=["users"],
)


@router.post("/users")
def get_users(session: Session = Depends(get_session)):
    return session.exec(select(User)).all()

@router.post("/login")
def login(data: LoginRequest, session: Session = Depends(get_session)):

    user = session.exec(
        select(User).where(User.username == data.username)
    ).first()

    if not user or not acs.verify_password(data.password, user.hash_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
        )
    access_token = acs.create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=30),
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
    )

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(acs.get_current_user_info)
):
    return current_user