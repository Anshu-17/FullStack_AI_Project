"""Database engine and session factory.

Works with a local PostgreSQL and with Supabase's SESSION pooler (port 5432):
- the URL is normalised in config.py (postgresql+psycopg:// prefix, sslmode=require for Supabase);
- the time zone is set with a SET command on every new connection (instead of a startup option, which
  connection poolers may reject), so timestamps always come back in UTC;
- psycopg's automatic server-side prepared statements are switched off when going through a Supabase
  pooler: they are fine in session mode, but break in transaction mode (port 6543) if someone uses that URL.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings


def connect_args_for(url: str) -> dict:
    parsed = make_url(url)
    through_pooler = "pooler.supabase.com" in (parsed.host or "") or parsed.port == 6543
    return {"prepare_threshold": None} if through_pooler else {}


engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args_for(settings.database_url))


@event.listens_for(engine, "connect")
def _use_utc(dbapi_connection, _record):
    """Every new connection: timestamps in UTC (+00:00), whatever the server's own time zone is."""
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'UTC'")
    dbapi_connection.commit()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
