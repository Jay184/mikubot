from discord import Interaction, Member
from discord.app_commands import describe, checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='youaregoingtobrazil', description='Sends a user to Brazil and gives them the Brazil role.')
    @checks.has_role(bot.settings.brazil.team_role_id)
    @checks.bot_has_permissions(send_messages=True)
    @describe(user='The user you want to send to Brazil.')
    async def handler(interaction: Interaction, user: Member):
        settings = bot.settings.brazil

        brazil_role = await interaction.guild.fetch_role(settings.brazil_role_id)
        member_role = await interaction.guild.fetch_role(settings.member_role_id)

        existing_role = user.get_role(settings.brazil_role_id)

        if existing_role:
            await user.remove_roles(brazil_role)
            await user.add_roles(member_role)
            reply_text = f'{user.display_name} has been retrieved from Brazil!'
        else:
            await user.remove_roles(member_role)
            await user.add_roles(brazil_role)
            reply_text = f'{user.display_name} has been sent to Brazil!'

        await interaction.response.send_message(reply_text, ephemeral=True)  # noqa
