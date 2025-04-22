from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='hd', description='Hot Dog')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'https://cdn.discordapp.com/attachments/1008900328931995688/1040365318989688843/video0_1.mp4'
        await interaction.response.send_message(reply_text)  # noqa
