"""Alembic environment for crg.

The SQLAlchemy URL is supplied at runtime by ``GraphStore._init_schema()``
(via ``Config.set_main_option("sqlalchemy.url", ...)``) so the same env.py
is used for both production upgrades and pytest fixtures. We therefore do
not read a URL from ``alembic.ini`` — the ini value is intentionally empty.

Autogenerate is not used: migrations in this project are hand-authored
because the schema is owned by ``graph.py:_SCHEMA_SQL`` (the legacy
bootstrap kept as a smoke comparator) and we want the migration files to
be auditable line-for-line against that constant.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, event, pool

# Alembic Config object — values come from alembic.ini plus runtime
# overrides set by GraphStore._init_schema().
config = context.config

if config.config_file_name is not None:
    # ``disable_existing_loggers`` defaults to True, which sets
    # ``disabled = True`` on every logger created before this point --
    # including every ``crg.*`` logger, since the
    # package is imported long before any migration runs. The effect is
    # permanent for the life of the process: crg stops logging entirely,
    # silently, with no error.
    #
    # In production this never fired because ``GraphStore`` builds its
    # Alembic Config programmatically and leaves ``config_file_name``
    # unset. It fired in the test suite, where ``tests/test_alembic_*``
    # loads ``alembic.ini`` directly -- so from the first such test
    # onward, every log-based assertion in the run was testing a logger
    # that could not emit. Tests passed in isolation and silently lost
    # their teeth in the full run.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# No declarative metadata: schema is hand-authored in versions/.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live SQLite connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # pysqlite's legacy transaction handling commits before every DDL
    # statement, so each CREATE/ALTER landed as its own durable commit (31 on
    # a fresh graph DB) and a failure half-way left a partial revision behind
    # the previous version row. With pysqlite's handling off and an explicit
    # BEGIN, SQLite runs the whole upgrade as one transaction: one commit, and
    # a failed upgrade rolls back to the schema it started from.
    @event.listens_for(connectable, "connect")
    def _disable_pysqlite_transactions(dbapi_connection, _connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(connectable, "begin")
    def _begin_sqlite_transaction(connection):
        connection.exec_driver_sql("BEGIN")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite needs render_as_batch for ALTER TABLE in future revisions.
            render_as_batch=True,
            transactional_ddl=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
