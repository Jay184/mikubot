import asyncio
import logging
import msgpack
from loguru import logger
from sqlitedict import SqliteDict
from datetime import datetime, timezone
from discord import Client, Intents, Message, Thread, Member, Guild, User, Embed
from discord import Activity, ActivityType, AuditLogAction
from discord.utils import MISSING
from discord.app_commands import CommandTree
from contextlib import contextmanager
from .config import Settings
from .logger import InterceptHandler


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
        self.tree = CommandTree(self)
        self.settings = settings

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
        return super().run(
            token,
            reconnect=reconnect,
            log_handler=InterceptHandler(),
            log_formatter=log_formatter,
            log_level=log_level,
            root_logger=root_logger,
        )

    async def on_ready(self):
        logger.info(f'Logged on as {self.user}!')
        await self.change_presence(activity=Activity(type=ActivityType.listening, name='you'))
        await self.release_from_brazil()

    async def on_message(self, message: Message):
        # No self replies
        if message.author == self.user:
            return

        settings = self.settings.trigger_words

        if not settings.allow_threads and isinstance(message.channel, Thread):
            return

        is_ignored = message.author.get_role(settings.ignored_role_id)
        if message.author and is_ignored:
            logger.info(f'{message.author.display_name} ignored due to role.')
            return

        # Special trigger word in single channel
        if message.channel.id == settings.team_chat_1_id:
            if settings.team_trigger in message.content.lower():
                reply_text = f'Go to <#{settings.team_chat_2_id}> pls.'
                await message.reply(reply_text, delete_after=5.0)
                return

        for trigger in settings.triggers:
            if trigger.triggered(message.content):
                await message.reply(trigger.get_reply())

                with self.storage(table='statistics.triggers', autocommit=True) as db:
                    key = f'{message.author.id}::{trigger.pattern}'
                    db[key] = db.get(key, 0) + 1

                if not self.settings.trigger_words.allow_multiple:
                    return

    async def on_message_delete(self, message: Message):
        if message.author == self.user:
            return

        embed = self.create_log_embed(
            message.author,
            f'**Message deleted in <#{message.channel.id}>**\nID: {message.id}\n{message.content}',
            color=0xff0000,
        )

        channel = await self.fetch_channel(self.settings.logging_channel_id)
        await channel.send(embed=embed)

    async def on_message_edit(self, before: Message, after: Message):
        if before.author == self.user:
            return

        if before.content == after.content:
            return

        embed = self.create_log_embed(
            before.author,
            f'**[Message]({after.jump_url}) edit in <#{after.channel.id}>.**',
            color=0xffff00,
        )

        embed.add_field(
            name='Original message',
            value=before.content,
        )

        embed.add_field(
            name='Edited message',
            value=after.content,
        )

        channel = await self.fetch_channel(self.settings.logging_channel_id)
        await channel.send(embed=embed)

    async def on_member_join(self, member: Member):
        embed = self.create_log_embed(
            member,
            f'**{member.global_name} has joined the server!**\nUsers in server: {member.guild.member_count}',
            color=0x00ff00,
        )

        channel = await self.fetch_channel(self.settings.logging_channel_id)
        await channel.send(embed=embed)

    async def on_member_remove(self, member: Member):
        role_list = ', '.join(r.name for r in member.roles)

        embed = self.create_log_embed(
            member,
            f'**{member.global_name} has left the server!**\nRoles: {role_list}',
            color=0xff0000,
        )

        channel = await self.fetch_channel(self.settings.logging_channel_id)
        await channel.send(embed=embed)

    async def on_member_ban(self, guild: Guild, user: User | Member):
        log_entry = await anext(guild.audit_logs(action=AuditLogAction.ban))
        log_message = f'**{user.global_name} has been banned from the server.**'

        if log_entry.reason:
            log_message += f'\nReason: {log_entry.reason}'

        if log_entry.user:
            log_message += f'\nBy: ${log_entry.user.global_name}'

        embed = self.create_log_embed(
            user,
            log_message,
            color=0xff0000,
        )

        channel = await self.fetch_channel(self.settings.logging_channel_id)
        await channel.send(embed=embed)

    async def on_member_unban(self, guild: Guild, user: User | Member):
        log_entry = await anext(guild.audit_logs(action=AuditLogAction.unban))
        log_message = f'**{user.global_name} has been unbanned from the server.**'

        if log_entry.reason:
            log_message += f'\nReason: {log_entry.reason}'

        if log_entry.user:
            log_message += f'\nBy: ${log_entry.user.global_name}'

        embed = self.create_log_embed(
            user,
            log_message,
            color=0x00ff00,
        )

        channel = await self.fetch_channel(self.settings.logging_channel_id)
        await channel.send(embed=embed)

    async def setup_hook(self):
        import mikubot.commands as commands

        commands.sync.register(self)
        commands.settings.register(self)
        commands.code.register(self)
        commands.avatar.register(self)
        commands.clap.register(self)
        commands.dlc.register(self)
        commands.backup.register(self)
        commands.downgrade.register(self)
        commands.download.register(self)
        commands.drive.register(self)
        commands.edenpatch.register(self)
        commands.expatch.register(self)
        commands.gamebanana.register(self)
        commands.holybeans.register(self)
        commands.hotdog.register(self)
        commands.hitfan.register(self)
        commands.hatefrance.register(self)
        commands.install.register(self)
        commands.it.register(self)
        commands.link.register(self)
        commands.list_brazil.register(self)
        commands.localfiles.register(self)
        commands.modules.register(self)
        commands.purge.register(self)
        commands.rename_channel.register(self)
        commands.role.register(self)
        commands.songs.register(self)
        commands.toggle_bot_response.register(self)
        commands.upgrade.register(self)
        commands.user_count.register(self)
        commands.uwu.register(self)
        commands.wrongfolder.register(self)
        commands.you_are_going_to_brazil.register(self)
        commands.zoe.register(self)

        if self.settings.zoe.scan_enabled:
            logger.info('Scanning for Zoe messages.')
            scan_task = commands.zoe.scan_messages(self)
            asyncio.create_task(scan_task)

        # guild = await self.fetch_guild(1008898200184291389)
        # synced_commands = await self.tree.sync()
        # print(f'Synced {len(synced_commands)} commands.')

    async def release_from_brazil(self):
        settings = self.settings.brazil

        for guild in self.guilds:
            brazil_role = await guild.fetch_role(settings.brazil_role_id)
            member_role = await guild.fetch_role(settings.member_role_id)

            for member in brazil_role.members:
                await member.remove_roles(brazil_role)
                await member.add_roles(member_role)
                logger.info(f'{member.display_name} has been retrieved from Brazil!')

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
    def storage(self, table: str = None, *, autocommit: bool = False):
        table = table or '__unnamed__'

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
