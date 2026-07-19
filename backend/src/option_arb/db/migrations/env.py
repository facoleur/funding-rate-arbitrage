from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import models so metadata is populated.
from option_arb import db  # noqa: F401
from option_arb.db import models  # noqa: F401
from option_arb.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL with runtime settings (env-loaded) so migrations use the same DB
# as the app. Alembic's own sqlalchemy.url stays as a fallback for offline mode.
config.set_main_option("sqlalchemy.url", settings.resolved_alembic_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Alembic uses a sync driver (psycopg2 for postgres, plain sqlite3 for
    SQLite). Runtime uses async drivers separately."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
