from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def _normalize_database_url(database_url: str) -> str:
    # Allow startup in environments where psycopg2 is unavailable but psycopg is installed.
    if database_url.startswith("postgresql+psycopg2://"):
        try:
            __import__("psycopg2")
            return database_url
        except ModuleNotFoundError:
            try:
                __import__("psycopg")
                return database_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
            except ModuleNotFoundError:
                return database_url
    return database_url


engine = create_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
