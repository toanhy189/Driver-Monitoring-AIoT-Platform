from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from pwdlib import PasswordHash

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.core.db import get_session
from app.models.user import User
from app.core.config import settings


password_hash = PasswordHash.recommended()

ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta,) -> str:
    expire = datetime.now(UTC) + expires_delta

    payload = {
        "exp": expire,
        "sub": str(subject),
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )

def decode_access_token(token):
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=ALGORITHM
        )
        return payload["sub"]
    except JWTError:
        return None

def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)



oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def get_current_user_id(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
):
    user_id = decode_access_token(token)
    
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )
    return user_id

def get_current_user_info(
    session: Session = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
):
  #thừa  user_id = get_current_user_id()

    user = session.exec(
        select(User).where(User.id == int(user_id))
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user