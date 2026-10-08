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
from app.models.user import User


reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_STR}/users/login"
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

    user = session.get(User, int(user_id))

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed_roles: str):
    def role_checker(current_user: CurrentUser) -> User:
        if current_user.role not in allowed_roles:
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