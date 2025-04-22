from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='listbrazil', description='Lists all users who are currently stuck in Brazil.')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        brazil_role = await interaction.guild.fetch_role(bot.settings.brazil.brazil_role_id)
        member_names = ', '.join(m.display_name for m in brazil_role.members)

        reply_text = f'Users stuck in Brazil: {member_names}' if len(brazil_role.members) else 'No users are currently stuck in Brazil.'
        await interaction.response.send_message(reply_text)  # noqa
