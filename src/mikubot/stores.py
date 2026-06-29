from typing import ContextManager
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import sqlite3

from discord import Interaction, InteractionMessage

from .config import Settings


class VacationStore:
    def __init__(self, db_path: str | Path, settings: Settings) -> None:
        self.db_path = str(db_path)
        self.settings = settings

    def _get_connection(self) -> ContextManager[sqlite3.Connection]:
        @contextmanager
        def impl_():
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=5000;")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return impl_()

    @staticmethod
    def _ensure_table(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vacations (
                message INTEGER PRIMARY KEY,
                guild INTEGER NOT NULL,
                user INTEGER NOT NULL,
                channel INTEGER NOT NULL,

                delay REAL NOT NULL,
                start REAL NOT NULL,
                end REAL NOT NULL,
                special INTEGER NOT NULL,

                old_roles TEXT NOT NULL,
                new_roles TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_channel ON vacations(channel);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_special ON vacations(special);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_end ON vacations(end);")

    def store(
            self,
            delay: float,
            interaction: Interaction,
            message: InteractionMessage, *,
            special: bool = False,
    ) -> None:
        start = datetime.now(timezone.utc)
        end = start + timedelta(seconds=delay)

        guild = interaction.guild_id
        user = interaction.user.id
        channel = self.settings.rename_chat.target_channel_id

        def build_roles(primary, extra=None) -> str:
            return ",".join([str(primary)] + ([str(extra)] if extra else []))

        old_roles = build_roles(
            self.settings.brazil.member_role_id,
            self.settings.rename_chat.special_role_id if special else None,
        )

        new_roles = build_roles(
            self.settings.brazil.brazil_role_id,
            self.settings.brazil.special_brazil_role_id if special else None,
        )

        with self._get_connection() as conn:
            self._ensure_table(conn)

            conn.execute("""
                INSERT OR REPLACE INTO vacations (
                    message, guild, user, channel, delay,
                    start, end, special, old_roles, new_roles
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message.id,
                guild,
                user,
                channel,
                delay,
                start.timestamp(),
                end.timestamp(),
                1 if special else 0,
                old_roles,
                new_roles,
            ))

    def remove_entry(self, message_id: int):
        with self._get_connection() as conn:
            self._ensure_table(conn)
            conn.execute("DELETE FROM vacations WHERE message = ?", (message_id,))

    def list_entries(
            self,
            *,
            channel: int | None = None,
            special: bool | None = None,
            expired: bool | None = None,
            now: float | None = None,
    ) -> list[dict]:
        now = now if now is not None else datetime.now(timezone.utc).timestamp()

        query = "SELECT * FROM vacations WHERE 1=1"
        params = []

        if channel is not None:
            query += " AND channel = ?"
            params.append(channel)

        if special is not None:
            query += " AND special = ?"
            params.append(1 if special else 0)

        if expired:
            query += " AND end < ?"
            params.append(now)
        elif expired is False:
            query += " AND end >= ?"
            params.append(now)

        with self._get_connection() as conn:
            self._ensure_table(conn)
            cur = conn.execute(query, params)
            rows = cur.fetchall()

        return [{
            "message": r[0],
            "guild": r[1],
            "user": r[2],
            "channel": r[3],

            "delay": r[4],
            "start": r[5],
            "end": r[6],
            "special": bool(r[7]),

            "old_roles": map(int, r[8].split(",")),
            "new_roles": map(int, r[9].split(",")),
        } for r in rows]


class CounterStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    def _get_connection(self) -> ContextManager[sqlite3.Connection]:
        @contextmanager
        def impl_():
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=5000;")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return impl_()

    @staticmethod
    def _ensure_table(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
        """)

    def increment_counter(self, key: str) -> int:
        """
        Increment the counter for key and return the new value.
        """
        with self._get_connection() as conn:
            self._ensure_table(conn)

            conn.execute(
                """
                INSERT INTO counters (key, value)
                VALUES (?, 1)
                ON CONFLICT(key)
                DO UPDATE SET value = value + 1
                """,
                (key,),
            )

            cursor = conn.execute(
                "SELECT value FROM counters WHERE key = ?",
                (key,),
            )

            return cursor.fetchone()[0]

    def reset_counter(self, key: str) -> None:
        """
        Reset the counter to 0 for key.
        Creates the row if it does not exist.
        """
        with self._get_connection() as conn:
            self._ensure_table(conn)

            conn.execute(
                """
                INSERT INTO counters (key, value)
                VALUES (?, 0)
                ON CONFLICT(key)
                DO UPDATE SET value = 0
                """,
                (key,),
            )

    def get_value(self, key: str, default: int = 0) -> int:
        """
        Return the current counter value for key.

        If the row does not exist, return `default`.
        """
        with self._get_connection() as conn:
            self._ensure_table(conn)

            cursor = conn.execute(
                "SELECT value FROM counters WHERE key = ?",
                (key,),
            )

            row = cursor.fetchone()

            if row is None:
                return default

            return row[0]
