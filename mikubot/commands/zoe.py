import msgpack
import random
from datetime import datetime
from urllib.parse import urlparse
from discord import Interaction, Message, Embed
from discord.errors import NotFound
from discord.app_commands import checks
from sqlitedict import SqliteDict
from loguru import logger
from emoji import purely_emoji
from mikubot import Bot


def purely_url(s: str) -> bool:
    if not len(s):
        return False

    words = s.split()
    urls = []

    for word in words:
        parsed = urlparse(word)
        if parsed.scheme and parsed.netloc:
            urls.append(word)

    return len(words) == len(urls)


def is_valid(message: Message) -> bool:
    text = message.content.strip()
    return len(text) > 0 and not purely_emoji(text) and not purely_url(text)


async def scan_messages(bot: Bot):
    channel_ids = [(id_, True) for id_ in bot.settings.zoe.channels.public] + \
                  [(id_, False) for id_ in bot.settings.zoe.channels.private]

    channels = [(await bot.fetch_channel(id_), public) for id_, public in channel_ids]

    zoes = SqliteDict(
        bot.settings.zoe.database_file,
        tablename='messages',
        autocommit=False,
        encode=msgpack.dumps,
        decode=msgpack.loads,
        outer_stack=False,
    )

    last_messages = SqliteDict(
        bot.settings.zoe.database_file,
        tablename='last_messages',
        autocommit=False,
        encode=msgpack.dumps,
        decode=msgpack.loads,
        outer_stack=False,
    )

    for channel, public in channels:
        logger.info(f'Scanning #{channel.name} for messages.')

        unsaved = 0
        last = last_messages.get(str(channel.id))
        limit = None

        try:
            last_message = await channel.fetch_message(last) if last else None
        except NotFound:
            last_message = None
            limit = bot.settings.zoe.fallback_limit

        async for message in channel.history(limit=limit, after=last_message):
            if message.author.id == bot.settings.zoe.user_id and is_valid(message):
                data = {
                    'user': message.author.id,
                    'channel': message.channel.id,
                    'public': public,
                    'link': message.jump_url,
                    'content': message.content,
                    'ts': message.created_at.timestamp()
                }

                zoes[str(message.id)] = data
                unsaved += 1

            last = message.id

            if unsaved > 100:
                zoes.commit()
                unsaved = 0

        zoes.commit()

        last_messages[str(channel.id)] = last
        last_messages.commit()

    zoes.close()
    last_messages.close()


def register(bot: Bot):
    @bot.tree.command(name='zoe', description='Hits you with a random Zoe message.')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        zoe = await bot.fetch_user(bot.settings.zoe.user_id)
        is_public = interaction.channel_id in bot.settings.zoe.channels.public

        with SqliteDict(
            bot.settings.zoe.database_file,
            tablename='messages',
            autocommit=False,
            encode=msgpack.dumps,
            decode=msgpack.loads,
            outer_stack=False,
        ) as db:
            message = random.choice(list(db.values()))
            while not message.get('public') and is_public:
                message = random.choice(list(db.values()))

            jump_url = message.get('link')
            text = message.get('content')

            if len(text) > 256:
                text = text[:253] + '...'

            embed = Embed(
                title=text,
                description=f'[Source]({jump_url})',
                timestamp=datetime.fromtimestamp(message.get('ts')),
                color=0xff0000,
            )

            embed.set_author(name=zoe.display_name,
                             icon_url=zoe.avatar.url)

            await interaction.response.send_message(  # noqa
                embed=embed,
            )
