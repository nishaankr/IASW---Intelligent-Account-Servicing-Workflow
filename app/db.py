from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

_is_sqlite = settings.database_url.startswith("sqlite") # special arg for sqlLite
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,

    pool_pre_ping=not _is_sqlite, #needed for postgres but not for SqlLite
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_session() -> Generator[Session, None, None]:
    #Yield a DB session and confirm that it's closed. so that when fastAPI starts a session, multiple users dont exhaut the connection limit

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() #this creats fresh sessions for each request and then closes them after use

        