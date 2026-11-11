from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def create_sqlite_engine(db_path: Path) -> Engine:
    """Engine for the single SQLite file that holds all application data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        # Web requests and the background worker run on different threads.
        connect_args={"check_same_thread": False, "timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets the UI keep reading while the worker writes.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
