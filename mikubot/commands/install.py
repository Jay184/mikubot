from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='install', description='Mod installation guide')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'https://gamebanana.com/tuts/15379'
        await interaction.response.send_message(reply_text)  # noqa
