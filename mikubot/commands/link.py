from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='link', description='Links to click on to download Eden Project.')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'https://cdn.discordapp.com/attachments/1008978799989362808/1078429246151741500/image.png'
        await interaction.response.send_message(reply_text)  # noqa
