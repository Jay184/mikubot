from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot

from .utils import is_admin_or_owner


def register(bot: Bot):
    @bot.tree.command(name="sync", description="Syncs commands.")
    @is_admin_or_owner(bot.settings.owner_id)
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        commands = await bot.tree.sync()
        response_message = f"Synced {len(commands)} app commands."

        await interaction.response.send_message(  # noqa
            response_message,
            ephemeral=True,
        )
