from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='hf', description='Hit Fan')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'https://cdn.discordapp.com/attachments/1009649075227984062/1044486785679507536/video0.mov'
        await interaction.response.send_message(reply_text)  # noqa
