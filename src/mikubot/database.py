from functools import lru_cache
from typing import Generator
from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine, Session


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


@lru_cache
def get_engine(database_url: str) -> Engine:
    # pool_pre_ping avoids stale connections in long-running apps
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    # Attach to `engine.sync_engine` when using async
    @event.listens_for(engine, identifier="connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    return engine


def get_session(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
