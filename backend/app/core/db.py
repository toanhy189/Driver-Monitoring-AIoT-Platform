from sqlmodel import Session, create_engine

from app.core.config import settings


engine = create_engine(
    str(settings.DATABASE_URL),
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
)

def get_session():
    with Session(engine) as session:
        yield session
