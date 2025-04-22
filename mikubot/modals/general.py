from discord import Interaction
from discord.ui import TextInput
from .base import SettingsModal


class GeneralSettingsModal(SettingsModal, title='General settings'):
    unused = TextInput(
        label='Nothing here yet',
        required=True,
    )

    async def on_submit(self, interaction: Interaction):
        await super().on_submit(interaction)
