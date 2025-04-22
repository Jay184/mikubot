from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='download', description='Eden Project download link')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        reply_text = '''\
**Eden Project Full Version**
https://gamebanana.com/mods/405848
        
**Lite Version**
For more details, use /lite
https://gamebanana.com/mods/427167
'''

        await interaction.response.send_message(reply_text)  # noqa
