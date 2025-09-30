from datetime import datetime, time, timedelta, timezone


def next_occurrence(target_time: time) -> datetime:
    now = datetime.now(timezone.utc)
    next_dt = now.replace(hour=target_time.hour, minute=target_time.minute,
                          second=target_time.second, microsecond=target_time.microsecond)
    if now >= next_dt:
        next_dt += timedelta(days=1)

    return next_dt
