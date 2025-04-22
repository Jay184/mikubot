import msgpack
import random
from discord import Interaction, Embed
from discord.app_commands import checks
from mikubot import Bot
from sqlitedict import SqliteDict
from datetime import datetime
from loguru import logger


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
        last_message = await channel.fetch_message(last) if last else None

        async for message in channel.history(limit=None, after=last_message):
            if message.author.id == bot.settings.zoe.user_id:
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

            embed = Embed(
                title=f'Link',
                description=message.get('content'),
                url=jump_url,
                timestamp=datetime.fromtimestamp(message.get('ts')),
                color=0xff0000,
            )

            embed.set_author(name=zoe.display_name,
                             icon_url=zoe.avatar.url)

            await interaction.response.send_message(  # noqa
                embed=embed,
            )
