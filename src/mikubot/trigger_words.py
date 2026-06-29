from typing import ContextManager
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from discord import Message, Member, Thread

from .config import TriggerWordSettings


class TriggerWordHandler:
    table_name = "statistics_triggers"

    def __init__(self, db_path: str | Path, settings: TriggerWordSettings):
        self.settings = settings
        self.db_path = str(db_path)

    def create_statistics_table(self) -> None:
        with self._get_connection() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    user_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, keyword)
                );
            """)

    def increment_counter(self, user_id: int, keyword: str) -> None:
        with self._get_connection() as conn:
            conn.execute(f"""
                INSERT INTO {self.table_name} (user_id, keyword, count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, keyword)
                DO UPDATE SET count = count + 1;
            """, (user_id, keyword))

    def should_trigger(self, message: Message) -> bool:
        is_ignored_by_bot = isinstance(message.author, Member) and message.author.get_role(self.settings.ignored_role_id)
        return self.settings.enabled and not is_ignored_by_bot

    async def handle(self, message: Message) -> None:
        if not self.settings.allow_threads and isinstance(message.channel, Thread):
            return

        if not self.should_trigger(message):
            return

        # Special trigger word in single channel
        await self._handle_special_channel(message)

        for trigger in self.settings.triggers:
            if trigger.triggered(message.content):
                reply_text = trigger.get_reply()

                if not reply_text:
                    continue

                await message.reply(reply_text)

                self.increment_counter(message.author.id, trigger.key or trigger.pattern)

                if not self.settings.allow_multiple:
                    return

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

    async def _handle_special_channel(self, message: Message) -> None:
        is_correct_channel = message.channel.id == self.settings.team_chat_1_id
        is_correct_keyword = self.settings.team_trigger in message.content.lower()

        if is_correct_channel and is_correct_keyword:
            await message.reply(
                f"Go to <#{self.settings.team_chat_2_id}> pls.",
                delete_after=5.0,
            )
