from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='sync', description='Syncs commands.')
    @checks.has_permissions(administrator=True)
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        commands = await bot.tree.sync()
        response_message = f'Synced {len(commands)} app commands.'

        await interaction.response.send_message(  # noqa
            response_message,
            ephemeral=True,
        )

    @handler.error
    async def error_handler(interaction: Interaction, error):
        await interaction.response.send_message(  # noqa
            str(error),
            ephemeral=True,
        )
