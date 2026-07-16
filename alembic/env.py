"""Alembic environment — async (asyncpg) aware.

The database URL comes from application settings, and the target metadata is the
shared declarative ``Base`` so future autogenerate sees every model.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import get_settings
from app.db import Base

config = context.config
if config.config_file_name is not None:
    # `disable_existing_loggers=False` — the default (True) silences every
    # logger that already exists when this runs, which in-process (the test
    # harness migrates via `alembic upgrade head`, and the container migrates
    # before serving) means every `app.*` logger goes quiet for the rest of the
    # process. Nothing warns; logs just stop. Alembic's own config only wants to
    # add its loggers, never to gag the application's.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_url() -> str:
    # Honour an explicit override (tests migrate a specific DB via
    # ``Config.set_main_option``); otherwise use the owner DSN from settings.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
