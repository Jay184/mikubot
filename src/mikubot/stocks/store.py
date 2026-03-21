from pathlib import Path
from sqlitedict import SqliteDict, SqliteMultithread


class MarketStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def initialize(self):
        """Ensure required history tables exist."""
        self._create_price_history_table()
        self._create_balance_history_table()

    def lookup(self, domain: str, key: str) -> dict | None:
        """Return dict value or None (keeps previous behavior)."""
        with SqliteDict(self.db_path, domain) as db:
            return db.get(key)

    def store(self, domain: str, key: str, value: dict):
        """Store a JSON-serializable mapping in the given domain."""
        with SqliteDict(self.db_path, domain) as db:
            db[key] = value
            db.commit()

    def domain(self, domain: str) -> dict[str, dict]:
        """Return a dict of all items in a domain (be careful with very large domains)."""
        with SqliteDict(self.db_path, domain) as db:
            return {k: v for k, v in db.items()}

    def remove(self, domain: str, key: str) -> bool:
        """Remove key from domain; return True if removed, False otherwise."""
        with SqliteDict(self.db_path, domain) as db:
            if key in db:
                del db[key]
                db.commit()
                return True

        return False

    def execute(self, sql: str, params: tuple | None = None) -> None:
        """Execute a statement and close connection afterward."""
        conn = self._get_conn()
        try:
            conn.execute(sql, params or ())
            conn.commit()
        finally:
            conn.close()

    def executemany(self, sql: str, param_rows: list[tuple | None]) -> None:
        """Execute statements and close connection afterward."""
        conn = self._get_conn()
        try:
            conn.executemany(sql, param_rows)
            conn.commit()
        finally:
            conn.close()

    def select(self, sql: str, params: tuple | None = None) -> list[tuple]:
        """Run a select and return a consumed list of rows (connection closed)."""
        conn = self._get_conn()
        rows = list(conn.select(sql, params or ()))
        conn.close()
        return rows

    def _get_conn(self) -> SqliteMultithread:
        return SqliteMultithread(self.db_path, False, True, False)

    def _create_price_history_table(self):
        sql = """
            CREATE TABLE IF NOT EXISTS price_history (
                security_key TEXT NOT NULL,
                timestamp INTEGER NOT NULL,  -- Unix timestamp in seconds
                price REAL NOT NULL,
                PRIMARY KEY (security_key, timestamp),
                FOREIGN KEY (security_key) REFERENCES securities(key)
            );
        """
        self.execute(sql)

    def _create_balance_history_table(self):
        sql = """
            CREATE TABLE IF NOT EXISTS balance_history (
                user_id TEXT NOT NULL,
                timestamp INTEGER NOT NULL,  -- Unix timestamp in seconds
                balance REAL NOT NULL,
                PRIMARY KEY (user_id, timestamp),
                FOREIGN KEY (user_id) REFERENCES portfolios(key)
            );
        """
        self.execute(sql)
