from discord import Interaction
from discord.app_commands import describe, checks, choices, Choice
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='role', description='Gives you a role.')
    @checks.bot_has_permissions(send_messages=True, manage_roles=True)
    @describe(role='The role you want to give yourself.')
    @choices(role=[
        Choice(name=k, value=str(v)) for k, v in bot.settings.choosable_roles.roles.items()
    ])
    async def handler(interaction: Interaction, role: Choice[str]):
        new_role = await interaction.guild.fetch_role(int(role.value))

        old_roles = (interaction.guild.get_role(int(_id)) for _id in bot.settings.choosable_roles.roles.values())
        await interaction.user.remove_roles(*old_roles)
        await interaction.user.add_roles(new_role)

        await interaction.response.send_message(f'Added {new_role.name}', ephemeral=True)  # noqa
