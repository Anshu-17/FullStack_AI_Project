"""Database engine and session factory."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# TimeZone=UTC: timestamps come back as UTC (+00:00) whatever the database server's own time zone is,
# so the API, the UI and exports all show the same, unambiguous times.
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args={"options": "-c TimeZone=UTC"})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
