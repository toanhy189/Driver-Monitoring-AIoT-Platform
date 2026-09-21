from sqlmodel import Field, SQLModel

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    fullname: str
    username: str
    hash_password: str
    email: str
    phone: str
    role: str = "Customer"