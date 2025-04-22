from discord import Interaction
from discord.ui import TextInput
from pydantic import TypeAdapter
from .base import SettingsModal, Bot


class GamebananaSearchModal(SettingsModal, title='Gamebanana search settings'):
    limit = TextInput(
        label='Limit',
        placeholder='10',
        default='10',
        required=True,
    )

    full = TextInput(
        label='Full output',
        placeholder='true',
        default='true',
        required=True,
    )

    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.limit.default = bot.settings.gamebanana_search.limit
        self.full.default = bot.settings.gamebanana_search.full

    async def on_submit(self, interaction: Interaction):
        settings = self.bot.settings.gamebanana_search

        settings.limit = TypeAdapter(int).validate_strings(self.limit.value)
        settings.full = TypeAdapter(bool).validate_strings(self.full.value)
        self.bot.settings.save()

        await super().on_submit(interaction)
