from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='backup', description='Tutorial on backing up MM+ save data.')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'https://gamebanana.com/tuts/15701'
        await interaction.response.send_message(reply_text)  # noqa
