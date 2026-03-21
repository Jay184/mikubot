from typing import Any, Generator
from loguru import logger
from sqlitedict import SqliteDict
from datetime import datetime, timezone
from discord import Client, Intents, Message, Thread, Member, User, Guild, Embed, Interaction
from discord import Activity, ActivityType, AuditLogAction
from discord.utils import MISSING
from discord.app_commands import CommandTree, errors
from contextlib import contextmanager
import asyncio
import logging
import msgpack

from .config import Settings
from .logger import InterceptHandler
from .stocks.core import Market


class CustomCommandTree(CommandTree):
    async def on_error(self, interaction: Interaction, error: errors.AppCommandError) -> None:
        await super().on_error(interaction, error)
        logger.error(error)

        if isinstance(error, errors.CheckFailure):
            await interaction.response.send_message(  # noqa
                "You're missing privileges to run this command.",
                ephemeral=True,
            )
            return

        if isinstance(error, errors.CommandOnCooldown):
            await interaction.response.send_message(  # noqa
                f"Command is on cooldown. {round(error.retry_after, 2)} seconds left.",
                ephemeral = True,
            )
            return

        if isinstance(error, errors.CommandInvokeError):
            await interaction.response.send_message(  # noqa
                str(error.original),
                ephemeral=True,
            )
            return


class Bot(Client):
    def __init__(self, settings: Settings, **options):
        intents = Intents(
            guilds=True,
            guild_messages=True,
            moderation=True,
            presences=True,
            reactions=True,
            members=True,
            message_content=True,
        )

        super().__init__(intents=intents, **options)
        self.tree = CustomCommandTree(self)
        self.settings = settings
        self.market = Market(settings.market)
        self.market_executor = None

    def run(
        self,
        token: str,
        *,
        reconnect: bool = True,
        log_handler: logging.Handler | None = MISSING,
        log_formatter: logging.Formatter = MISSING,
        log_level: int = MISSING,
        root_logger: bool = False,
    ):
        log_level = logger.level(self.settings.logging.level).no if log_level is MISSING else log_level

        return super().run(
            token,
            reconnect=reconnect,
            log_handler=InterceptHandler(),
            log_formatter=log_formatter,
            log_level=log_level,
            root_logger=root_logger,
        )

    async def on_ready(self):
        logger.info(f"Logged on as {self.user}!")
        await self.change_presence(activity=Activity(type=ActivityType.listening, name="you"))
        await self.release_from_brazil()

    async def on_message(self, message: Message):
        # No self replies
        if message.author == self.user:
            return

        settings = self.settings.trigger_words

        if not settings.allow_threads and isinstance(message.channel, Thread):
            return

        is_ignored = isinstance(message.author, Member) and message.author.get_role(settings.ignored_role_id)
        if is_ignored:
            logger.info(f"{message.author.display_name} ignored due to role.")
            return

        # Special trigger word in single channel
        if message.channel.id == settings.team_chat_1_id:
            if settings.team_trigger in message.content.lower():
                reply_text = f"Go to <#{settings.team_chat_2_id}> pls."
                await message.reply(reply_text, delete_after=5.0)
                return

        for trigger in settings.triggers:
            if trigger.triggered(message.content):
                reply_text = trigger.get_reply()

                if not reply_text:
                    continue

                await message.reply(reply_text)

                with self.storage(table="statistics.triggers", autocommit=True) as db:
                    key = f"{message.author.id}::{trigger.pattern}"
                    db[key] = db.get(key, 0) + 1

                if not self.settings.trigger_words.allow_multiple:
                    return

    async def on_message_delete(self, message: Message):
        if message.author == self.user:
            return

        if message.author.id in self.settings.logging.excluded_users:
            return

        embed = self.create_log_embed(
            message.author,
            f"**Message deleted in <#{message.channel.id}>**\nID: `{message.id}`\n{message.content}",
            color=0xff0000,
        )

        channel = await self.fetch_channel(self.settings.logging.channel_id)
        await channel.send(embed=embed)

    async def on_message_edit(self, before: Message, after: Message):
        if before.author == self.user:
            return

        if before.author.id in self.settings.logging.excluded_users:
            return

        if before.content == after.content:
            return

        embed = self.create_log_embed(
            before.author,
            f"**[Message]({after.jump_url}) edit in <#{after.channel.id}>.**",
            color=0xffff00,
        )

        embed.add_field(
            name="Original message",
            value=before.content,
        )

        embed.add_field(
            name="Edited message",
            value=after.content,
        )

        channel = await self.fetch_channel(self.settings.logging.channel_id)
        await channel.send(embed=embed)

    async def on_member_join(self, member: Member):
        if member.id in self.settings.logging.excluded_users:
            return

        embed = self.create_log_embed(
            member,
            f"**{member.global_name} has joined the server!**\nUsers in server: {member.guild.member_count}",
            color=0x00ff00,
        )

        channel = await self.fetch_channel(self.settings.logging.channel_id)
        await channel.send(embed=embed)

    async def on_member_remove(self, member: Member):
        if member.id in self.settings.logging.excluded_users:
            return

        role_list = ", ".join(r.name for r in member.roles)

        embed = self.create_log_embed(
            member,
            f"**{member.global_name} has left the server!**\nRoles: {role_list}",
            color=0xff0000,
        )

        channel = await self.fetch_channel(self.settings.logging.channel_id)
        await channel.send(embed=embed)

    async def on_member_ban(self, guild: Guild, user: User | Member):
        if user.id in self.settings.logging.excluded_users:
            return

        log_entry = await anext(guild.audit_logs(action=AuditLogAction.ban))
        log_message = f"**{user.global_name} has been banned from the server.**"

        if log_entry.reason:
            log_message += f"\nReason: {log_entry.reason}"

        if log_entry.user:
            log_message += f"\nBy: {log_entry.user.mention}"

        embed = self.create_log_embed(
            user,
            log_message,
            color=0xff0000,
        )

        channel = await self.fetch_channel(self.settings.logging.channel_id)
        await channel.send(embed=embed)

    async def on_member_unban(self, guild: Guild, user: User | Member):
        if user.id in self.settings.logging.excluded_users:
            return

        log_entry = await anext(guild.audit_logs(action=AuditLogAction.unban))
        log_message = f"**{user.global_name} has been unbanned from the server.**"

        if log_entry.reason:
            log_message += f"\nReason: {log_entry.reason}"

        if log_entry.user:
            log_message += f"\nBy: {log_entry.user.mention}"

        embed = self.create_log_embed(
            user,
            log_message,
            color=0x00ff00,
        )

        channel = await self.fetch_channel(self.settings.logging.channel_id)
        await channel.send(embed=embed)

    async def setup_hook(self):
        import mikubot.commands as commands
        from .stocks.command import register as register_stock_market

        commands.sync.register(self)
        commands.stop.register(self)
        commands.reply_commands.register(self)
        commands.settings.register(self)
        commands.code.register(self)
        commands.avatar.register(self)
        commands.clap.register(self)
        commands.edenpatch.register(self)
        commands.gamebanana.register(self)
        commands.it.register(self)
        commands.list_brazil.register(self)
        commands.purge.register(self)
        commands.rename_channel.register(self)
        commands.role.register(self)
        commands.toggle_bot_response.register(self)
        commands.user_count.register(self)
        commands.uwu.register(self)
        commands.you_are_going_to_brazil.register(self)
        commands.zoe.register(self)
        commands.guess.register(self)
        commands.goofy_translate.register(self)
        register_stock_market(self)

        if self.settings.market.enabled:
            logger.info("Starting stock market.")

            if not self.market_executor:
                self.market_executor = self.market.tx_engine.executor_loop(interval=self.settings.market.executor_interval)
                asyncio.create_task(self.market_executor)

        if self.settings.zoe.scan_enabled:
            logger.info("Scanning for Zoe messages.")
            scan_task = commands.zoe.scan_messages(self)
            asyncio.create_task(scan_task)

        if self.settings.sync_commands:
            # guild = await self.fetch_guild(1008898200184291389)
            synced_commands = await self.tree.sync()
            logger.info(f"Synced {len(synced_commands)} commands.")

    async def release_from_brazil(self):
        settings = self.settings.brazil

        with self.storage(table="brazil_vacationers") as db:
            for guild in self.guilds:
                brazil_role = await guild.fetch_role(settings.brazil_role_id)
                member_role = await guild.fetch_role(settings.member_role_id)
                special_role = await guild.fetch_role(self.settings.rename_chat.special_role_id)
                special_brazil_role = await guild.fetch_role(settings.special_brazil_role_id)

                for member in brazil_role.members:
                    await member.remove_roles(brazil_role)
                    await member.add_roles(member_role)
                    logger.info(f"{member.display_name} has been retrieved from Brazil!")

                    if f"{guild.id}:{member.id}" in db:
                        del db[f"{guild.id}:{member.id}"]

                for member in special_brazil_role.members:
                    await member.remove_roles(special_brazil_role)
                    await member.add_roles(special_role)
                    await member.add_roles(member_role)
                    logger.info(f"{member.display_name} has been retrieved from Brazil!")

                    if f"{guild.id}:{member.id}" in db:
                        del db[f"{guild.id}:{member.id}"]

            db.commit()

    def create_log_embed(self, subject: Member, description: str = None, *, color: int = None) -> Embed:
        embed = Embed(
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        embed.set_author(
            name=subject.global_name,
            icon_url=subject.avatar.url if subject.avatar else None,
        )

        embed.set_footer(
            text=self.user.display_name,
            icon_url=self.user.avatar.url,
        )

        return embed

    @contextmanager
    def storage(self, table: str = None, *, autocommit: bool = False) -> Generator[SqliteDict, Any, None]:
        table = table or "__unnamed__"

        try:
            yield SqliteDict(
                self.settings.storage_file,
                tablename=table,
                encode=msgpack.dumps,
                decode=msgpack.loads,
                autocommit=autocommit,
                outer_stack=False,
            )
        finally:
            pass
