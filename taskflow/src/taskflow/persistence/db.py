# taskflow/persistence/db.py

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    # Dual-write is best-effort and awaited inline in TaskQueue - without a
    # connect timeout, a Postgres outage stalls every task update for the OS
    # TCP timeout (measured ~4s) instead of failing fast into the existing
    # log-and-continue path.
    return create_async_engine(
        database_url, pool_pre_ping=True, connect_args={"timeout": 3}
    )


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
