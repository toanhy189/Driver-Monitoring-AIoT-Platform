from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    fullname: str
    username: str
    password: str
    email: str
    phone: str
