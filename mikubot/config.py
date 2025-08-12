from typing import Self
from datetime import time
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
import os
import random
import re

from .stocks import Security


class MikuBotBaseModel(BaseModel):
    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,  # Allows 'timeOfDay' to fill 'time_of_day'
        serialize_by_alias=True,  # Serializes 'time_of_day' to 'timeOfDay'
        alias_generator=to_camel,
        extra='ignore',
    )


class MegaMixCodeSettings(MikuBotBaseModel):
    max_length: int = 0x80
    allowed_role: int
    binaries: list[str] = Field(default_factory=list)


class UwufySettings(MikuBotBaseModel):
    stutter_chance: float = 0.09
    face_chance: float = 0.03
    action_chance: float = 0.5
    exclamation_chance: float = 0.95
    nsfw_actions: bool = False
    nsfw_channels: list[int] = Field(default_factory=list)
    power: int = 3


class GamebananaSearchSettings(MikuBotBaseModel):
    limit: int = 10
    full: bool = True


class ChoosableRoleSettings(MikuBotBaseModel):
    roles: dict[str, int]


class BrazilSettings(MikuBotBaseModel):
    brazil_role_id: int
    special_brazil_role_id: int
    member_role_id: int
    team_role_id: int


class RenameChatSettings(MikuBotBaseModel):
    success_chance: float = 0.02
    roll_time: float = 3.0
    failure_delay: float = 3.0
    min_minutes: float = 3.0
    max_minutes: float = 60

    keep_messages: bool = True
    deletion_delay: float = 5.0
    single_message: bool = True
    ephemeral_messages: bool = False

    target_channel_id: int
    loading_role_id: int
    special_role_id: int

    streak_postfixes: dict[int, str] = Field(default_factory=dict)
    retrieval_messages: list[str] = Field(default_factory=list)

    def lowest_postfix(self, streak: int) -> str | None:
        keys = sorted(self.streak_postfixes.keys(), reverse=True)

        for key in keys:
            if streak >= key:
                return self.streak_postfixes[key].format(streak=streak)

    def random_delay(self) -> float:
        minutes_range = self.max_minutes - self.min_minutes
        value = random.random() ** 3
        return (value * minutes_range + self.min_minutes) * 60.0


class TriggerWordReply(MikuBotBaseModel):
    text: str
    weight: int = 1


class TriggerWord(MikuBotBaseModel):
    pattern: str
    replies: list[TriggerWordReply] = Field(default_factory=list)
    text: str | None = None

    def triggered(self, text: str) -> bool:
        match = re.search(self.pattern, text, re.IGNORECASE)
        return match is not None

    def get_reply(self) -> str | None:
        all_texts = [reply.text for reply in self.replies]
        all_weights = [reply.weight for reply in self.replies]

        if self.text:
            all_texts.append(self.text)
            all_weights.append(sum(all_weights) or 1)

        if len(all_texts) == len(all_weights) and all_texts and any(all_weights):
            return random.choices(all_texts, all_weights, k=1)[0]

        return None


class TriggerWordSettings(MikuBotBaseModel):
    enabled: bool = True
    allow_threads: bool = True
    allow_multiple: bool = False
    ignored_role_id: int
    triggers: list[TriggerWord]
    team_chat_1_id: int
    team_chat_2_id: int
    team_trigger: str


class ZoeChannelSettings(MikuBotBaseModel):
    public: list[int] = Field(default_factory=list)
    private: list[int] = Field(default_factory=list)


class ZoeQuotesSettings(MikuBotBaseModel):
    database_file: str
    user_id: int
    scan_enabled: bool = True
    fallback_limit: int = 100
    channels: ZoeChannelSettings = ZoeChannelSettings()


class GuessingGameSettings(MikuBotBaseModel):
    emoji_pool: list[str]
    sequence_length: int = 4
    max_duplicates: int = 2


class StockMarketSettings(MikuBotBaseModel):
    enabled: bool = False
    required_role: int
    market_file: str
    market_maker_id: int
    interest_rate: float = 0.01
    order_fee: float = 0.99
    order_fee_rate: float = 0.00
    starting_credit: float = 100.0
    open_time: time = time(7, 30, 0)
    close_time: time = time(23, 0, 0)
    executor_interval: float = 5.0
    hide_portfolio_securities: bool = False
    starting_securities: list[Security] = Field(default_factory=list)


class LoggingSettings(MikuBotBaseModel):
    file_path: str = 'log.log'
    rotation: str = '500 MB',
    retention: str = '10 days'
    channel_id: int
    excluded_users: list[int] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
        env_prefix='mikubot_',
        extra='ignore'
    )

    discord_key: str = None
    storage_file: str
    logging: LoggingSettings
    trigger_words: TriggerWordSettings
    rename_chat: RenameChatSettings
    brazil: BrazilSettings
    choosable_roles: ChoosableRoleSettings
    gamebanana_search: GamebananaSearchSettings
    uwufy: UwufySettings
    mm_code: MegaMixCodeSettings
    zoe: ZoeQuotesSettings
    market: StockMarketSettings
    guessing_game: GuessingGameSettings

    @staticmethod
    def file_path() -> str:
        return os.environ.get('MIKUBOT_SETTINGS_FILE', 'settings.json')

    def save(self):
        with open(self.file_path(), mode='w', encoding='utf-8') as f:
            f.write(self.model_dump_json(indent=4, by_alias=True, exclude={'discord_key'}))

    @classmethod
    def load(cls) -> Self:
        with open(cls.file_path(), mode='r', encoding='utf-8') as f:
            return cls.model_validate_json(f.read())
