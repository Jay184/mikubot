from discord import Interaction
from discord.ui import TextInput
from pydantic import TypeAdapter
from .base import SettingsModal, Bot


class TriggerWordModal(SettingsModal, title='Trigger word settings'):
    enabled = TextInput(
        label='Enabled',
        placeholder='true',
        default='true',
        required=True,
    )

    allow_threads = TextInput(
        label='Allow in threads',
        placeholder='true',
        default='true',
        required=True,
    )

    allow_multiple = TextInput(
        label='Allow multiple',
        placeholder='false',
        default='false',
        required=True,
    )

    ignored_role_id = TextInput(
        label='"Ignored" role ID',
        required=True,
    )

    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.enabled.default = bot.settings.trigger_words.enabled
        self.allow_threads.default = bot.settings.trigger_words.allow_threads
        self.allow_multiple.default = bot.settings.trigger_words.allow_multiple
        self.ignored_role_id.default = bot.settings.trigger_words.ignored_role_id

    async def on_submit(self, interaction: Interaction):
        settings = self.bot.settings.trigger_words

        settings.enabled = TypeAdapter(bool).validate_strings(self.enabled.value)
        settings.allow_threads = TypeAdapter(bool).validate_strings(self.allow_threads.value)
        settings.allow_multiple = TypeAdapter(bool).validate_strings(self.allow_multiple.value)
        settings.ignored_role_id = TypeAdapter(int).validate_strings(self.ignored_role_id.value)
        self.bot.settings.save()

        await super().on_submit(interaction)
