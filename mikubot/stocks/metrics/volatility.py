from typing import TYPE_CHECKING, Literal, Unpack, ClassVar
from abc import ABC, abstractmethod
from datetime import timedelta
from pydantic import BaseModel, ConfigDict
import statistics
import uuid

if TYPE_CHECKING:
    from .. import Transaction

from ..utils import current_timestamp, standard_model_config


class VolatilityStrategy(ABC, BaseModel):
    model_config = standard_model_config

    _subtypes: ClassVar[dict] = {}

    def __init_subclass__(cls, **kwargs: Unpack[ConfigDict]):
        cls._subtypes[cls.type] = cls

    @abstractmethod
    def calculate(self, transactions: list['Transaction']) -> float:
        return 0.0


class LastNVolatility(VolatilityStrategy):
    type: Literal['last_n'] = 'last_n'
    amount: int

    def calculate(self, transactions: list['Transaction']) -> float:
        if len(transactions) < self.amount + 1:
            return 0.0  # Not enough data

        # Calculate percentage changes
        prices = [tx.price for tx in transactions[-(self.amount + 1):]]
        returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

        # Standard deviation of returns
        return statistics.stdev(returns)


class TimeWindowVolatility(VolatilityStrategy):
    type: Literal['time_window'] = 'time_window'
    window: int | timedelta

    @property
    def window_seconds(self) -> int:
        return int(self.window.total_seconds()) if isinstance(self.window, timedelta) else self.window

    def calculate(self, transactions: list['Transaction']) -> float:
        window_start = current_timestamp().timestamp() - self.window_seconds
        filtered = [tx.price for tx in transactions if tx.execution_time.timestamp() >= window_start]

        if len(filtered) < 2:
            return 0.0  # Not enough data

        # Calculate percentage changes
        returns = [(filtered[i] - filtered[i - 1]) / filtered[i - 1] for i in range(1, len(filtered))]

        # Standard deviation of returns
        return statistics.stdev(returns)


class HybridVolatility(VolatilityStrategy):
    type: Literal['hybrid'] = 'hybrid'
    window: int | timedelta
    min_transactions: int
    fallback_n: int

    @property
    def window_seconds(self) -> int:
        return int(self.window.total_seconds()) if isinstance(self.window, timedelta) else self.window

    def calculate(self, transactions: list['Transaction']) -> float:
        window_start = current_timestamp().timestamp() - self.window_seconds

        # Get transactions in the window
        recent = [tx for tx in transactions if tx.execution_time.timestamp() >= window_start]

        if len(recent) >= self.min_transactions:
            prices = [tx.price for tx in recent]
        elif len(transactions) >= self.fallback_n + 1:
            prices = [tx.price for tx in transactions[-(self.fallback_n + 1):]]
        else:
            return 0.0  # Not enough data

        if len(prices) < 2:
            return 0.0

        returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
        return statistics.stdev(returns)


class VolatilityCache:
    def __init__(self, strategy: VolatilityStrategy):
        self.strategy = strategy
        self._last_transaction_ids: list[uuid.UUID] = []
        self._cached_volatility: float = 0.0

    def update(self, transactions: list['Transaction']) -> float:
        current_ids = [tx.id for tx in transactions[-(self.strategy.n + 1):]] \
            if isinstance(self.strategy, LastNVolatility) else [tx.id for tx in transactions]

        if current_ids == self._last_transaction_ids:
            return self._cached_volatility

        self._cached_volatility = self.strategy.calculate(transactions)
        self._last_transaction_ids = current_ids
        return self._cached_volatility
