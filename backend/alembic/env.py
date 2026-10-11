"""Alembic env — async Postgres (Neon) only. SQLite path needs no migrations."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

config = context.config


def _sa_url() -> str:
    u = (settings.database_url or "").strip()
    if u.lower().startswith(("postgresql://", "postgres://")):
        scheme, rest = u.split("://", 1)
        return f"postgresql+asyncpg://{rest}"
    return u  # postgresql+asyncpg:// passes through


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    if not settings.is_postgres:
        print("alembic: DATABASE_URL is not Postgres — nothing to migrate.")
        return
    engine = create_async_engine(_sa_url(), poolclass=None)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


asyncio.run(run_migrations_online())
