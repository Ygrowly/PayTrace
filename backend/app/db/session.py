"""Sync SQLAlchemy engine + session factory.

The runtime uses psycopg v3's *sync* driver. We deliberately avoid the async
engine in M0b because psycopg-async requires SelectorEventLoop on Windows
while uvicorn's default ProactorEventLoop is incompatible — and overriding
uvicorn's loop factory is brittle. A sync engine + `anyio.to_thread.run_sync`
in the readiness probe is simpler, portable, and sufficient for M0b's
health-check workload. Real DB access patterns are revisited in M2 if/when
concurrency demands it.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)

session_maker = sessionmaker(engine, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    with session_maker() as session:
        yield session
