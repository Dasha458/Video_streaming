"""
Do the migrations still build the schema the models describe?

Nothing checked. The integration tests create their schema with
``Base.metadata.create_all``, and CI never runs Alembic at all, so the
chain could have drifted from the models -- or stopped applying
altogether -- and the first anyone would hear of it is a deploy.

This runs the whole chain against a throwaway database and then asks
Alembic the same question ``--autogenerate`` asks: is there anything left
to generate? If there is, a model changed without a migration, or a
migration says something the models do not.
"""

from typing import Any, List

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

MIGRATION_DB = "migrations_under_test"

#: Differences worth failing over. compare_metadata also reports cosmetic
#: disagreements -- a server default spelled differently, a type Alembic
#: renders another way -- which would make this test noise rather than a
#: signal. A table or column that exists on one side and not the other is
#: never cosmetic.
STRUCTURAL = {
    "add_table",
    "remove_table",
    "add_column",
    "remove_column",
}


def _sync_url(async_url: str, database: str | None = None) -> str:
    """The container's URL for psycopg2, optionally pointing elsewhere."""
    url = async_url.replace("postgresql+asyncpg://", "postgresql://")
    if database is not None:
        url = url.rsplit("/", 1)[0] + f"/{database}"
    return url


def _describe(diff: Any) -> str:
    """Name the table and column, so a failure says what to go and fix."""
    kind = diff[0]
    if kind in ("add_table", "remove_table"):
        return f"{kind} {diff[1].name}"
    # ("add_column" | "remove_column", schema, table, Column)
    return f"{kind} {diff[2]}.{diff[3].name}"


def _structural(diffs: List[Any]) -> List[Any]:
    """Flatten Alembic's diff list and keep the structural entries."""
    out: List[Any] = []
    for diff in diffs:
        # Column diffs arrive as a list of tuples; table diffs as a tuple.
        entries = diff if isinstance(diff, list) else [diff]
        for entry in entries:
            if isinstance(entry, tuple) and entry and entry[0] in STRUCTURAL:
                out.append(entry)
    return out


@pytest.fixture
def migrated_url(postgres_url: str) -> Any:
    """A database with the migration chain applied to it, and nothing else."""
    admin = create_engine(_sync_url(postgres_url), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{MIGRATION_DB}"'))

    target = _sync_url(postgres_url, MIGRATION_DB)
    engine = create_engine(target)

    config = Config()
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", target)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    yield target

    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"'))
    admin.dispose()


def test_the_chain_applies_to_an_empty_database(migrated_url: str) -> None:
    """If this fails, `alembic upgrade head` fails on a fresh deploy."""
    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    assert version, "the chain left no version stamped"


def test_the_migrations_and_the_models_agree(migrated_url: str) -> None:
    """The check `--autogenerate` performs, as a test.

    A model changed without a migration shows up here as a column or table
    Alembic would add; a migration the models no longer describe shows up
    as one it would remove.
    """
    import src.models  # noqa: F401  (registers every table on Base.metadata)
    from src.infrastructure.database import Base

    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        diffs = _structural(compare_metadata(context, Base.metadata))
    engine.dispose()

    assert not diffs, "migrations have drifted from the models: " + "; ".join(
        _describe(d) for d in diffs
    )


def test_every_table_the_models_declare_exists(migrated_url: str) -> None:
    """Said plainly, so a failure names the table rather than a diff tuple."""
    from sqlalchemy import inspect

    import src.models  # noqa: F401
    from src.infrastructure.database import Base

    engine = create_engine(migrated_url)
    present = set(inspect(engine).get_table_names())
    engine.dispose()

    missing = sorted(set(Base.metadata.tables) - present)
    assert not missing, f"no migration creates: {', '.join(missing)}"
