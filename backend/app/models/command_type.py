from sqlmodel import Field, SQLModel


class CommandType(SQLModel, table=True):
    __tablename__ = "command_types"

    id: int | None = Field(
        default=None,
        primary_key=True,
    )

    code: str
    name: str
    description: str | None = None