from discord import Interaction
from discord.utils import MISSING
from discord.ui import Modal
from mikubot import Bot
import traceback


class SettingsModal(Modal):
    def __init__(
        self,
        bot: Bot,
        *,
        title: str = MISSING,
        timeout: float | None = None,
        custom_id: str = MISSING,
    ):
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)
        self.bot = bot

    async def on_submit(self, interaction: Interaction):
        success_message = 'Saved!'
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
            delete_after=3,
        )

    async def on_error(self, interaction: Interaction, error: Exception):
        error_message = 'Oops! Something went wrong.'
        await interaction.response.send_message(  # noqa
            error_message,
            ephemeral=True,
            delete_after=3,
        )
        traceback.print_exception(type(error), error, error.__traceback__)
