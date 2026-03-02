from typing import Self, Annotated, Literal
from datetime import time
from pathlib import Path
from functools import cached_property
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, ConfigDict, Field
from pydantic import PositiveInt, NonNegativeInt, PositiveFloat, NonNegativeFloat, HttpUrl
from pydantic import field_validator, BeforeValidator, PlainSerializer
from pydantic.alias_generators import to_camel
import os
import random
import re
import requests

from .stocks.models import SecurityConfig


type Probability = Annotated[float, Field(strict=True, ge=0, le=1)]
type NonEmptyString = Annotated[str, Field(min_length=1)]

type RawMultilineInput = str | list[str]

def join_lines(value: RawMultilineInput) -> str:
    if isinstance(value, list):
        return "\n".join(value)
    elif isinstance(value, str):
        return value

    raise ValueError("Expected string or a list of strings")


def split_lines(value: str) -> list[str]:
    return value.splitlines()


type MultilineText = Annotated[
    RawMultilineInput,
    BeforeValidator(join_lines),
    PlainSerializer(split_lines, return_type=list[str], when_used="json")
]


class MikuBotBaseModel(BaseModel):
    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,  # Allows "timeOfDay" to fill "time_of_day"
        serialize_by_alias=True,  # Serializes "time_of_day" to "timeOfDay"
        alias_generator=to_camel,
        extra="ignore",
    )


class MegaMixCodeSettings(MikuBotBaseModel):
    max_length: Annotated[int, Field(gt=0, le=0xFFFF, strict=True)] = 0x80
    allowed_role: PositiveInt
    binaries: Annotated[list[Path], Field(min_items=4, max_items=4, description="Exactly 4 paths to .exe binaries")]

    @field_validator("binaries", mode="after")  # noqa
    @classmethod
    def check_exe_suffix(cls, v: list[Path]) -> list[Path]:
        for path in v:
            if path.suffix.lower() != ".exe":
                raise ValueError(f"Invalid binary path '{path}': must end with .exe")
        return v


class UwufySettings(MikuBotBaseModel):
    stutter_chance: Probability = 0.09
    face_chance: Probability = 0.03
    action_chance: Probability = 0.5
    exclamation_chance: Probability = 0.95
    nsfw_actions: bool = False
    nsfw_channels: list[PositiveInt] = Field(default_factory=list)
    power: PositiveInt = 3


class GamebananaSearchSettings(MikuBotBaseModel):
    limit: PositiveInt = 10
    full: bool = True


class ChoosableRoleSettings(MikuBotBaseModel):
    roles: dict[NonEmptyString, PositiveInt]


class BrazilSettings(MikuBotBaseModel):
    brazil_role_id: PositiveInt
    special_brazil_role_id: PositiveInt
    member_role_id: PositiveInt
    team_role_id: PositiveInt


class LocalSource(BaseModel):
    source: Literal["local"]
    path: str


class UrlSource(BaseModel):
    source: Literal["url"]
    url: HttpUrl


type BannedSource = LocalSource | UrlSource


class RenameChatSettings(MikuBotBaseModel):
    enabled: bool = True
    success_chance: Probability = 0.02
    roll_time: NonNegativeFloat = 3.0
    failure_delay: NonNegativeFloat = 3.0
    min_minutes: PositiveFloat = 3.0
    max_minutes: PositiveFloat = 60.0

    keep_messages: bool = True
    deletion_delay: NonNegativeFloat = 5.0
    single_message: bool = True
    ephemeral_messages: bool = False

    target_channel_id: PositiveInt
    loading_role_id: PositiveInt
    special_role_id: PositiveInt

    streak_postfixes: dict[PositiveInt, str] = Field(default_factory=dict)
    retrieval_messages: list[str] = Field(default_factory=list)

    banned_word_sources: list[BannedSource] = Field(default_factory=list)

    @cached_property
    def banned_words(self) -> set[str]:
        words = set()

        for src in self.banned_word_sources:
            try:
                if isinstance(src, LocalSource):
                    path = Path(src.path)
                    if path.exists():
                        words.update(
                            w.strip().lower()
                            for w in path.read_text(encoding="utf-8").splitlines()
                            if w.strip()
                        )
                elif isinstance(src, UrlSource):
                    resp = requests.get(str(src.url), timeout=5)
                    if resp.ok:
                        words.update(
                            w.strip().lower()
                            for w in resp.text.splitlines()
                            if w.strip()
                        )
            except Exception as e:
                # Log but don’t crash the bot if one source fails
                print(f"[WARN] Failed to load banned words from {src}: {e}")

        return words

    def contains_banned(self, name: str) -> bool:
        tokens = re.split(r"[_\-\s]+", name.lower())
        return any(token in self.banned_words for token in tokens if token)

    def lowest_postfix(self, streak: int) -> str | None:
        keys = sorted(self.streak_postfixes.keys(), reverse=True)

        for key in keys:
            if streak >= key:
                return self.streak_postfixes[key].format(streak=streak)

    def random_delay(self) -> float:
        """
        Generate a random delay duration (in seconds) between the configured
        minimum and maximum delay times.
        """
        minutes_range = self.max_minutes - self.min_minutes
        value = random.random() ** 3
        return (value * minutes_range + self.min_minutes) * 60.0

    def random_retrieval_message(self) -> str | None:
        if not self.retrieval_messages:
            return None

        return random.choice(self.retrieval_messages)


class ReplyCommandConfig(MikuBotBaseModel):
    name: str
    description: str
    text: MultilineText
    enabled: bool = True
    ephemeral: bool = False


class TriggerWordReply(MikuBotBaseModel):
    text: MultilineText
    weight: NonNegativeInt = 1


class TriggerWord(MikuBotBaseModel):
    pattern: NonEmptyString
    replies: list[TriggerWordReply] = Field(default_factory=list)
    text: MultilineText | None = None

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
    ignored_role_id: PositiveInt
    triggers: list[TriggerWord]
    team_chat_1_id: PositiveInt
    team_chat_2_id: PositiveInt
    team_trigger: str


class ZoeChannelSettings(MikuBotBaseModel):
    public: list[PositiveInt] = Field(default_factory=list)
    private: list[PositiveInt] = Field(default_factory=list)


class ZoeQuotesSettings(MikuBotBaseModel):
    database_file: Path
    user_id: PositiveInt
    scan_enabled: bool = True
    fallback_limit: PositiveInt = 100
    channels: ZoeChannelSettings = ZoeChannelSettings()


class GuessingGameSettings(MikuBotBaseModel):
    emoji_pool: Annotated[list[NonEmptyString], Field(min_length=1)]
    sequence_length: Annotated[int, Field(ge=2, lt=10)] = 4
    max_duplicates: NonNegativeInt = 2


class StockMarketSettings(MikuBotBaseModel):
    enabled: bool = False
    required_role: PositiveInt | None = None
    admins: list[PositiveInt] = Field(default_factory=list)
    market_file: Path
    market_maker_id: PositiveInt | None = None
    interest_rate: NonNegativeFloat = 0.01
    order_fee: NonNegativeFloat = 0.99
    order_fee_rate: NonNegativeFloat = 0.00
    starting_credit: NonNegativeFloat = 100.0
    open_time: time = time(7, 30, 0)
    close_time: time = time(23, 0, 0)
    executor_interval: PositiveFloat = 5.0
    remote_update_interval: PositiveFloat = 3600.0
    local_update_interval: PositiveFloat = 60.0
    hide_portfolio_securities: bool = False
    securities: list[SecurityConfig] = Field(default_factory=list)

    @field_validator("securities", mode="after")  # noqa
    @classmethod
    def check_unique_tickers(cls, v: list[SecurityConfig]) -> list[SecurityConfig]:
        seen = set()
        unique_securities = []

        for sec in v:
            if sec.key not in seen:
                seen.add(sec.key)
                unique_securities.append(sec)
            else:
                # Optional: log warning
                #print(f"⚠️ Duplicate security key '{sec.key}' found — ignoring duplicate.")
                ...

        return unique_securities


class LoggingSettings(MikuBotBaseModel):
    file_path: Path = "logs/{time:YYYY-MM-DD}.log"
    rotation: str = "500 MB"
    retention: str = "10 days"
    level: NonNegativeInt | str = "INFO"
    backtrace: bool = False
    diagnose: bool = False
    channel_id: PositiveInt
    excluded_users: list[PositiveInt] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
        env_prefix="mikubot_",
        extra="ignore"
    )

    discord_key: str = None
    storage_file: Path
    owner_id: int | None = None
    restart_exit_code: int = 39
    sync_commands: bool = True
    logging: LoggingSettings
    trigger_words: TriggerWordSettings
    reply_commands: list[ReplyCommandConfig] = Field(default_factory=list)
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
        return os.environ.get("MIKUBOT_SETTINGS_FILE", "settings.json")

    def save(self):
        with open(self.file_path(), mode="w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=4, by_alias=True, exclude={"discord_key"}))

    @classmethod
    def load(cls) -> Self:
        with open(cls.file_path(), mode="r", encoding="utf-8") as f:
            return cls.model_validate_json(f.read())
