from discord import Interaction
from discord.ui import TextInput
from pydantic import TypeAdapter
from .base import SettingsModal, Bot


class UwufyModal(SettingsModal, title='Uwufy settings'):
    stutter_chance = TextInput(
        label='Stutter chance',
        required=True,
    )

    face_chance = TextInput(
        label='Face face',
        required=True,
    )

    action_chance = TextInput(
        label='Action chance',
        required=True,
    )

    exclamation_chance = TextInput(
        label='Exclamation chance',
        required=True,
    )

    power = TextInput(
        label='Power',
        required=True,
    )

    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.stutter_chance.default = str(bot.settings.uwufy.stutter_chance)
        self.face_chance.default = str(bot.settings.uwufy.face_chance)
        self.action_chance.default = str(bot.settings.uwufy.action_chance)
        self.exclamation_chance.default = str(bot.settings.uwufy.exclamation_chance)
        self.power.default = str(bot.settings.uwufy.power)

    async def on_submit(self, interaction: Interaction):
        settings = self.bot.settings.uwufy
        adapter = TypeAdapter(float)

        settings.stutter_chance = adapter.validate_strings(self.stutter_chance.value)
        settings.face_chance = adapter.validate_strings(self.face_chance.value)
        settings.action_chance = adapter.validate_strings(self.action_chance.value)
        settings.exclamation_chance = adapter.validate_strings(self.exclamation_chance.value)
        settings.power = TypeAdapter(int).validate_strings(self.power.value)
        self.bot.settings.save()

        await super().on_submit(interaction)
