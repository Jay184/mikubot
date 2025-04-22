from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='drive', description='Google Drive bypass')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = 'Due to a lot of people downloading our mods, the Google Drive has been capped. Follow this video to get around it! https://www.youtube.com/watch?v=u-v9SI3vFmE'
        await interaction.response.send_message(reply_text)  # noqa
