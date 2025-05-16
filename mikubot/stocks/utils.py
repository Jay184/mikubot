from datetime import datetime, timedelta, timezone
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel


def current_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def next_month() -> datetime:
    return current_timestamp() + timedelta(days=30)


standard_model_config = ConfigDict(
    validate_by_name=True,
    validate_by_alias=True,  # Allows 'timeOfDay' to fill 'time_of_day'
    serialize_by_alias=True,  # Serializes 'time_of_day' to 'timeOfDay'
    alias_generator=to_camel,
    extra='ignore',
)
