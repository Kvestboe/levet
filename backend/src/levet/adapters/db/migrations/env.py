"""Alembic environment.

The application runs migrations itself at start-up and hands this script an
open connection. When Alembic is run from the command line (for example
``alembic revision --autogenerate``) no connection is given and the database
is located from LEVET_DATA_DIR instead.
"""

import os
from pathlib import Path

from alembic import context
from sqlalchemy import Connection

from levet.adapters.db.engine import create_sqlite_engine
from levet.adapters.db.models import Base

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things in place; batch mode rebuilds the table.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported")

provided: Connection | None = context.config.attributes.get("connection")
if provided is not None:
    _run(provided)
else:
    data_dir = Path(os.environ.get("LEVET_DATA_DIR", "data"))
    with create_sqlite_engine(data_dir / "levet.db").begin() as connection:
        _run(connection)
