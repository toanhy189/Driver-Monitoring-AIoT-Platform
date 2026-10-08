from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import require_admin

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import app.core.security as acs
from app.core.db import get_session
from app.models.user import User
from app.schemas.user import LoginRequest, RegisterRequest
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.get("/")
def get_users(current_user: Annotated[User, Depends(require_admin)],session: Session = Depends(get_session)):
    return session.exec(select(User)).all()

@router.post("/login")
def login(data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),):

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

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register")
def register(
    data: RegisterRequest,
    session: Session = Depends(get_session),   
):
    existing_username = session.exec(
        select(User).where(User.username== data.username)
    ).first()
    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username already exists",
        )

    existing_email = session.exec(
        select(User).where(User.email == data.email)
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already exists",
        )

    existing_phone = session.exec(
        select(User).where(User.phone == data.phone)
    ).first()

    if existing_phone:
        raise HTTPException(
            status_code=400,
            detail="Phone already exists",
        )

    user = User(
        fullname=data.fullname,
        username=data.username,
        hash_password=acs.get_password_hash(data.password),
        email=data.email,
        phone=data.phone,
        role="VIEWER",
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return {
        "message": "Register successfully",
        "user": {
            "id": user.id,
            "fullname": user.fullname,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
        },
    }