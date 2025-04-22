from discord import Interaction
from discord.ui import TextInput
from pydantic import TypeAdapter
from .base import SettingsModal, Bot


class RenameChatModal1(SettingsModal, title='Rename chat settings (1)'):
    success_chance = TextInput(
        label='Success Chance',
        placeholder='0.02',
        default='0.02',
        required=True,
    )

    roll_time = TextInput(
        label='Roll delay',
        placeholder='3.0',
        default='3.0',
        required=True,
    )

    failure_delay = TextInput(
        label='Delay after failure',
        placeholder='3.0',
        default='3.0',
        required=True,
    )

    min_minutes = TextInput(
        label='Minimum minutes',
        placeholder='3.0',
        default='3.0',
        required=True,
    )

    max_minutes = TextInput(
        label='Maximum minutes',
        placeholder='60.0',
        default='60.0',
        required=True,
    )

    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.success_chance.default = str(bot.settings.rename_chat.success_chance)
        self.roll_time.default = str(bot.settings.rename_chat.roll_time)
        self.failure_delay.default = str(bot.settings.rename_chat.failure_delay)
        self.min_minutes.default = str(bot.settings.rename_chat.min_minutes)
        self.max_minutes.default = str(bot.settings.rename_chat.max_minutes)

    async def on_submit(self, interaction: Interaction):
        settings = self.bot.settings.rename_chat
        adapter = TypeAdapter(float)

        settings.success_chance = adapter.validate_strings(self.success_chance.value)
        settings.roll_time = adapter.validate_strings(self.roll_time.value)
        settings.failure_delay = adapter.validate_strings(self.failure_delay.value)
        settings.min_minutes = adapter.validate_strings(self.min_minutes.value)
        settings.max_minutes = adapter.validate_strings(self.max_minutes.value)
        self.bot.settings.save()

        await super().on_submit(interaction)


class RenameChatModal2(SettingsModal, title='Rename chat settings (2)'):
    current_streak = TextInput(
        label='Current streak',
        required=True,
    )

    target_channel_id = TextInput(
        label='Channel ID',
        required=True,
    )

    loading_role_id = TextInput(
        label='Rolling role ID',
        required=True,
    )

    special_role_id = TextInput(
        label='"Special" role ID',
        required=True,
    )

    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.current_streak.default = str(bot.settings.rename_chat.current_streak)
        self.target_channel_id.default = str(bot.settings.rename_chat.target_channel_id)
        self.loading_role_id.default = str(bot.settings.rename_chat.loading_role_id)
        self.special_role_id.default = str(bot.settings.rename_chat.special_role_id)

    async def on_submit(self, interaction: Interaction):
        settings = self.bot.settings.trigger_words
        adapter = TypeAdapter(int)

        settings.current_streak = adapter.validate_strings(self.current_streak.value)
        settings.target_channel_id = adapter.validate_strings(self.target_channel_id.value)
        settings.loading_role_id = adapter.validate_strings(self.loading_role_id.value)
        settings.special_role_id = adapter.validate_strings(self.special_role_id.value)
        self.bot.settings.save()

        await super().on_submit(interaction)
