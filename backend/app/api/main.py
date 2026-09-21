from fastapi import APIRouter

#from app.api.routes import items, login, private, users, utils
#from app.core.config import settings

#api_router = APIRouter()
#api_router.include_router(login.router)


# if settings.FASTAPI_ENV == "development":
#     api_router.include_router(private.router)

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()

password = "123456"
hashed = password_hash.hash(password)

print(hashed)