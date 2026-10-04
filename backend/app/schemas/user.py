from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    fullname: str
    username: str
    email: str
    phone: str
    role: str