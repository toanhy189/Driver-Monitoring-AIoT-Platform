from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.core.logging_config import request_method_context, request_path_context
from app.models.user import User
from app.services.audit_service import log_action


reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_STR}/login"
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(
    session: SessionDep,
    token: TokenDep,
) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[security.ALGORITHM],
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        user_id = int(user_id)
        if user_id <= 0:
            raise ValueError("Invalid user ID")
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = session.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed_roles: str):
    def role_checker(current_user: CurrentUser) -> User:
        role = {"Admin": "ADMIN", "Employee": "OPERATOR", "Customer": "VIEWER"}.get(
            current_user.role, current_user.role
        )
        if role not in allowed_roles:
            path = request_path_context.get()
            # Them audit cho 403 co actor, nhung giu signature mot tham so cua role_checker.
            if path != "-":
                with Session(engine) as audit_session:
                    log_action(
                        session=audit_session,
                        user_id=current_user.id,
                        action="PERMISSION_DENIED",
                        entity_type="Route",
                        entity_id=path,
                        details={
                            "method": request_method_context.get(),
                            "path": path,
                            "role": current_user.role,
                            "result": "denied",
                        },
                    )
                    audit_session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        return current_user

    return role_checker


def require_admin(current_user: CurrentUser) -> User:
    return require_role("ADMIN")(current_user)


def require_operator(current_user: CurrentUser) -> User:
    return require_role("ADMIN", "OPERATOR")(current_user)


def require_viewer(current_user: CurrentUser) -> User:
    return require_role("ADMIN", "OPERATOR", "VIEWER")(current_user)
