from datetime import datetime, timedelta
from enum import Enum
import matplotlib.dates as mdates


class SecurityIntervals(str, Enum):
    day = "day"
    week = "week"
    month = "month"


class IntervalData:
    def __init__(self, label: str, start: datetime, end: datetime, freq: str, tick_format: str, locator: mdates.ticker.Locator, margin: timedelta):
        self.label = label
        self.start = start
        self.end = end
        self.freq = freq
        self.tick_format = tick_format
        self.locator = locator
        self.margin = margin


class DayIntervalData(IntervalData):
    def __init__(self, end: datetime):
        start = end - timedelta(days=1)

        super().__init__(
            label="1D",
            start=start.replace(second=0, microsecond=0),
            end=end,
            freq="5min",
            tick_format="%H:%M",
            locator=mdates.HourLocator(interval=3),
            margin=timedelta(hours=2),
        )


class WeekIntervalData(IntervalData):
    def __init__(self, end: datetime):
        start = end - timedelta(days=7)

        super().__init__(
            label="1W",
            start=start.replace(minute=0, second=0, microsecond=0),
            end=end,
            freq="1h",
            tick_format="%a",
            locator=mdates.DayLocator(),
            margin=timedelta(hours=12),
        )


class MonthIntervalData(IntervalData):
    def __init__(self, end: datetime):
        start = end - timedelta(days=30)
        super().__init__(
            label="1M",
            start=start.replace(hour=0, minute=0, second=0, microsecond=0),
            end=end,
            freq="12h",
            tick_format="%d-%b",
            locator=mdates.DayLocator(interval=3),
            margin=timedelta(days=1),
        )
