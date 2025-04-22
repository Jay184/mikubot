from discord import Interaction
from discord.ui import TextInput
from pydantic import TypeAdapter
from .base import SettingsModal, Bot


class ZoeQuoteModal(SettingsModal, title='Trigger word settings'):
    database_file = TextInput(
        label='Database file',
        required=True,
    )

    user_id = TextInput(
        label='Zoe\'s user ID',
        required=True,
    )

    scan_enabled = TextInput(
        label='Enable scanning',
        placeholder='true',
        default='true',
        required=True,
    )

    def __init__(self, bot: Bot):
        super().__init__(bot)

        self.database_file.default = bot.settings.zoe.database_file
        self.user_id.default = str(bot.settings.zoe.user_id)
        self.scan_enabled.default = bot.settings.zoe.scan_enabled

    async def on_submit(self, interaction: Interaction):
        settings = self.bot.settings.zoe

        settings.database_file = self.database_file.value
        settings.user_id = TypeAdapter(int).validate_strings(self.user_id.value)
        settings.scan_enabled = TypeAdapter(bool).validate_strings(self.scan_enabled.value)
        self.bot.settings.save()

        await super().on_submit(interaction)
