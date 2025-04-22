from discord import Interaction
from discord.ui import TextInput
from pydantic import TypeAdapter
from .base import SettingsModal, Bot


class BrazilModal(SettingsModal, title='Brazil settings'):
    brazil_role_id = TextInput(
        label='Current streak',
        required=True,
    )

    special_brazil_role_id = TextInput(
        label='Channel ID',
        required=True,
    )

    member_role_id = TextInput(
        label='Rolling role ID',
        required=True,
    )

    team_role_id = TextInput(
        label='"Special" role ID',
        required=True,
    )

    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.brazil_role_id.default = str(bot.settings.brazil.brazil_role_id)
        self.special_brazil_role_id.default = str(bot.settings.brazil.special_brazil_role_id)
        self.member_role_id.default = str(bot.settings.brazil.member_role_id)
        self.team_role_id.default = str(bot.settings.brazil.team_role_id)

    async def on_submit(self, interaction: Interaction):
        settings = self.bot.settings.brazil
        adapter = TypeAdapter(int)

        settings.brazil_role_id = adapter.validate_strings(self.brazil_role_id.value)
        settings.special_brazil_role_id = adapter.validate_strings(self.special_brazil_role_id.value)
        settings.member_role_id = adapter.validate_strings(self.member_role_id.value)
        settings.team_role_id = adapter.validate_strings(self.team_role_id.value)
        self.bot.settings.save()

        await super().on_submit(interaction)
