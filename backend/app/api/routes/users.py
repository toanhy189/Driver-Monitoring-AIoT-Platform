from datetime import timedelta
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

import app.core.security as acs
from app.api.deps import get_current_user, require_admin, require_viewer
from app.core.config import settings
from app.core.db import get_session
from app.models.device import Device
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.device import DeviceResponse
from app.schemas.user import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.schemas.user import ProfileUpdate, PasswordChange, UserAdminUpdate, UserAdminCreate
from app.services.audit_service import log_action


router = APIRouter(tags=["users"])
logger = logging.getLogger(__name__)


@router.get("/users", response_model=list[UserResponse])
def get_users(
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    return session.exec(select(User)).all()


@router.get("/users/{user_id}/devices", response_model=list[DeviceResponse])
def get_user_devices(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    devices = session.exec(
        select(Device)
        .join(UserDevice, UserDevice.device_id == Device.id)
        .where(UserDevice.user_id == user_id, UserDevice.unassigned_at.is_(None))
        .distinct()
    ).all()
    return [DeviceResponse.from_device(device) for device in devices]


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(
        select(User).where(User.username == data.username)
    ).first()

    if not user or user.status != "ACTIVE" or not acs.verify_password(data.password, user.hash_password):
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
        session_version=user.session_version,
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
    user = _new_user(data, session)
    _commit_new_user(session, user)
    return {
        "message": "Register successfully",
        "user": UserResponse.model_validate(user, from_attributes=True),
    }


def _new_user(data: RegisterRequest, session: Session, role: str = "Customer"):
    if not data.username.strip() or not data.fullname.strip() or not 8 <= len(data.password) <= 128:
        raise HTTPException(status_code=422, detail="Name, username and password are invalid")
    if "@" not in data.email or " " in data.email:
        raise HTTPException(status_code=422, detail="Email is invalid")
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
        role=role,
    )
    session.add(user)
    return user


def _commit_new_user(session: Session, user: User):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Account already exists") from None
    session.refresh(user)


def invalidate_sessions(user_id: int):
    from app.services.ws_tickets import revoke_tickets
    from app.services.websocket_manager import manager
    revoke_tickets(user_id)
    manager.close_user_from_thread(user_id)


@router.put("/me", response_model=UserResponse)
def update_profile(data: ProfileUpdate, current_user: User = Depends(require_viewer),
                   session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.id == current_user.id).with_for_update()).one()
    if not data.fullname.strip() or "@" not in data.email or " " in data.email:
        raise HTTPException(status_code=422, detail="Invalid profile")
    for field in ("email", "phone"):
        if session.exec(select(User).where(getattr(User, field) == getattr(data, field),
                                          User.id != current_user.id)).first():
            raise HTTPException(status_code=409, detail=f"{field} already exists")
    user.fullname, user.email, user.phone = data.fullname.strip(), data.email.strip(), data.phone
    session.add(user)
    log_action(session, current_user.id, "UPDATE_PROFILE", "User", str(current_user.id))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Profile already exists") from None
    session.refresh(user)
    return user


@router.post("/me/password", status_code=204)
def change_password(data: PasswordChange, current_user: User = Depends(require_viewer),
                    session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.id == current_user.id).with_for_update()).one()
    if not acs.verify_password(data.current_password, user.hash_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    user.hash_password = acs.get_password_hash(data.new_password)
    user.session_version += 1
    session.add(user)
    log_action(session, user.id, "CHANGE_PASSWORD", "User", str(user.id))
    session.commit()
    invalidate_sessions(user.id)
    return Response(status_code=204)


@router.post("/logout", status_code=204)
def logout(current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.id == current_user.id).with_for_update()).one()
    user.session_version += 1
    session.add(user)
    log_action(session, user.id, "LOGOUT", "User", str(user.id))
    session.commit()
    invalidate_sessions(user.id)
    return Response(status_code=204)


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(data: UserAdminCreate, current_user: User = Depends(require_admin),
                session: Session = Depends(get_session)):
    if len(data.password) < 8 or len(data.password) > 128 or not data.username.strip():
        raise HTTPException(status_code=422, detail="Username and password are invalid")
    user = _new_user(data, session, role=data.role)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Account already exists") from None
    log_action(session, current_user.id, "CREATE_USER", "User", str(user.id), {"role": user.role})
    _commit_new_user(session, user)
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, data: UserAdminUpdate, current_user: User = Depends(require_admin),
                session: Session = Depends(get_session)):
    if not data.model_fields_set or any(getattr(data, name) is None for name in data.model_fields_set):
        raise HTTPException(status_code=422, detail="A role or status is required")
    # Lock admins in a stable order so concurrent demotions cannot remove the last admin.
    admins = session.exec(select(User).where(User.role.in_(["Admin", "ADMIN"]))
                          .order_by(User.id).with_for_update()
                          .execution_options(populate_existing=True)).all()
    actor = next((item for item in admins if item.id == current_user.id), None)
    if actor is None or actor.status != "ACTIVE" or actor.session_version != current_user.session_version:
        raise HTTPException(status_code=401, detail="Administrator session changed")
    user = session.exec(select(User).where(User.id == user_id).with_for_update()
                        .execution_options(populate_existing=True)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    role, state = data.role or user.role, data.status or user.status
    if user.id == current_user.id and (role != user.role or state != "ACTIVE"):
        raise HTTPException(status_code=409, detail="Cannot disable or change your own administrator role")
    if user.role in {"Admin", "ADMIN"} and user.status == "ACTIVE" and (role not in {"Admin", "ADMIN"} or state != "ACTIVE"):
        if sum(item.status == "ACTIVE" for item in admins) <= 1:
            raise HTTPException(status_code=409, detail="The last active administrator must remain")
    changed = (user.role, user.status) != (role, state)
    user.role, user.status = role, state
    if changed:
        user.session_version += 1
    session.add(user)
    log_action(session, current_user.id, "UPDATE_USER", "User", str(user.id), {"role": role, "status": state})
    session.commit()
    if changed:
        invalidate_sessions(user.id)
    return user


@router.put("/users/{user_id}/devices/{device_id}", response_model=DeviceResponse)
def assign_device(user_id: int, device_id: int, current_user: User = Depends(require_admin),
                  session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Active user not found")
    device = session.exec(select(Device).where(Device.id == device_id).with_for_update()).first()
    if device is None or device.lifecycle_state == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Device unavailable for assignment")
    active = session.exec(select(UserDevice).where(UserDevice.user_id == user_id,
        UserDevice.device_id == device_id, UserDevice.unassigned_at.is_(None))).first()
    if active is None:
        session.add(UserDevice(user_id=user_id, device_id=device_id))
        log_action(session, current_user.id, "ASSIGN_DEVICE", "Device", str(device_id), {"target_user_id": user_id})
    session.commit()
    session.refresh(device)
    return DeviceResponse.from_device(device)


@router.delete("/users/{user_id}/devices/{device_id}", status_code=204)
def unassign_device(user_id: int, device_id: int, current_user: User = Depends(require_admin),
                    session: Session = Depends(get_session)):
    from datetime import datetime, timezone
    device = session.exec(select(Device).where(Device.id == device_id).with_for_update()).first()
    if device is None or session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User or device not found")
    for assignment in session.exec(select(UserDevice).where(UserDevice.user_id == user_id,
        UserDevice.device_id == device_id, UserDevice.unassigned_at.is_(None))).all():
        assignment.unassigned_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.add(assignment)
    log_action(session, current_user.id, "UNASSIGN_DEVICE", "Device", str(device_id), {"target_user_id": user_id})
    session.commit()
    from app.services.websocket_manager import manager
    manager.close_user_from_thread(user_id)
    return Response(status_code=204)
