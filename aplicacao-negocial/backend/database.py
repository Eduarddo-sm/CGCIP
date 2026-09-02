from pathlib import Path

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import settings


NEGOCIAL_SCHEMA = "negocial"


def is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def is_postgres_url(database_url: str) -> bool:
    return database_url.startswith(("postgresql", "postgres"))


def _ensure_sqlite_directory(database_url: str):
    if not database_url.startswith("sqlite:///"):
        return
    path = database_url.replace("sqlite:///", "", 1)
    Path(path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_directory(settings.database_url)

IS_SQLITE = is_sqlite_url(settings.database_url)
IS_POSTGRES = is_postgres_url(settings.database_url)
DB_SCHEMA = NEGOCIAL_SCHEMA if IS_POSTGRES else None

connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine_kwargs = {"pool_pre_ping": True} if IS_POSTGRES else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    **engine_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    metadata = MetaData(schema=DB_SCHEMA)
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
