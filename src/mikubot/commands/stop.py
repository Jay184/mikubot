from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot
import sys

from .utils import is_admin_or_owner


def register(bot: Bot):
    @bot.tree.command(name="stop", description="Stop the bot completely.")
    @is_admin_or_owner(bot.settings.owner_id)
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        await interaction.response.send_message(  # noqa
            "🛑 Stopping bot...",
            ephemeral=True,
        )
        await bot.close()
        sys.exit(0)

    @bot.tree.command(name="restart", description="Restart the bot process")
    @is_admin_or_owner(bot.settings.owner_id)
    @checks.bot_has_permissions(send_messages=True)
    async def restart(interaction: Interaction):
        await interaction.response.send_message(  # noqa
            "🔄 Restarting bot...",
            ephemeral=True,
        )
        await bot.close()
        sys.exit(bot.settings.restart_exit_code)
