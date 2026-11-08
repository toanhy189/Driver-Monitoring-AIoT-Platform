from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


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
    status: str = "ACTIVE"


class RegisterRequest(BaseModel):
    fullname: str
    username: str
    password: str
    confirm_password: str
    email: str
    phone: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fullname: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    phone: str = Field(pattern=r"^\+?[0-9]{5,20}$")


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["Admin", "Employee", "Customer"] | None = None
    status: Literal["ACTIVE", "DISABLED"] | None = None


class UserAdminCreate(RegisterRequest):
    role: Literal["Admin", "Employee", "Customer"] = "Customer"
