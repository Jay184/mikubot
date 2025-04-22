from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='wrongfolder', description='Wrong Folder')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'https://i.imgur.com/xpuxXeq.gif'
        await interaction.response.send_message(reply_text)  # noqa
