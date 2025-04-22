from discord import Interaction, Message
from discord.app_commands import describe, checks
from mikubot import Bot
import re


def register(bot: Bot):
    @bot.tree.command(name='clap', description='Adds 👏 Clap 👏 Emoji 👏 in 👏 between 👏 each 👏 word.')
    @checks.bot_has_permissions(send_messages=True)
    @describe(text='The text you want to add claps to.')
    async def handler(interaction: Interaction, text: str):
        text = re.sub(r'\s+', ' 👏 ', text)
        await interaction.response.send_message(text)  # noqa

    @bot.tree.context_menu(name='clap')
    @checks.bot_has_permissions(send_messages=True)
    async def context_handler(interaction: Interaction, message: Message):
        text = re.sub(r'\s+', ' 👏 ', message.content)
        await interaction.response.send_message(text, allowed_mentions=None)  # noqa
