from datetime import timedelta
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import app.core.security as acs
from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.core.db import get_session
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.services.audit_service import log_action


router = APIRouter(tags=["users"])
logger = logging.getLogger(__name__)


@router.get("/users", response_model=list[UserResponse])
def get_users(
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    return session.exec(select(User)).all()


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(
        select(User).where(User.username == data.username)
    ).first()

    if not user or not acs.verify_password(data.password, user.hash_password):
        # Login sai truoc day khong tao audit; chi ghi user_id neu tai khoan ton tai.
        if user is not None:
            log_action(
                session=session,
                user_id=user.id,
                action="LOGIN_FAILED",
                entity_type="User",
                entity_id=str(user.id),
                details={"result": "denied"},
            )
            session.commit()
        # Tai khoan khong ton tai khong co actor DB; ghi event toi thieu va khong ghi username.
        logger.warning(
            "Authentication failed",
            extra={
                "event": "login_failed",
                "result": "denied",
                "user_id": user.id if user is not None else None,
            },
        )
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = acs.create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    # Login thanh cong truoc day chi phat token; audit them actor va ket qua, khong ghi token.
    log_action(
        session=session,
        user_id=user.id,
        action="LOGIN_SUCCESS",
        entity_type="User",
        entity_id=str(user.id),
        details={"result": "success"},
    )
    session.commit()
    return LoginResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/register", status_code=201)
def register(data: RegisterRequest, session: Session = Depends(get_session)):
    if not data.email.strip():
        raise HTTPException(status_code=400, detail="Email cannot be blank")
    if not data.phone.strip():
        raise HTTPException(status_code=400, detail="Phone number cannot be blank")
    if not data.phone.isdigit():
        raise HTTPException(status_code=400, detail="Phone number must be numeric")
    if data.password != data.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

    if session.exec(select(User).where(User.username == data.username)).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    if session.exec(select(User).where(User.email == data.email)).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    if session.exec(select(User).where(User.phone == data.phone)).first():
        raise HTTPException(status_code=409, detail="Phone already exists")

    user = User(
        fullname=data.fullname,
        username=data.username,
        hash_password=acs.get_password_hash(data.password),
        email=data.email,
        phone=data.phone,
        role="Customer",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return {
        "message": "Register successfully",
        "user": UserResponse.model_validate(user, from_attributes=True),
    }
