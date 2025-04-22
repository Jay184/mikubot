from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='hb', description='Holy Beans')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'https://cdn.discordapp.com/attachments/1009649075227984062/1044484546822938684/video0.mp4'
        await interaction.response.send_message(reply_text)  # noqa
