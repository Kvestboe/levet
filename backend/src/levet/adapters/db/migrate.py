from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(engine: Engine) -> None:
    """Bring the database up to the latest schema. Safe to call on every start."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
