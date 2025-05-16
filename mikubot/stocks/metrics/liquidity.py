from typing import TYPE_CHECKING, Literal, Unpack, ClassVar
from abc import ABC, abstractmethod
from datetime import timedelta
from pydantic import BaseModel, ConfigDict
import uuid

if TYPE_CHECKING:
    from .. import Transaction

from ..utils import current_timestamp, standard_model_config


class LiquidityStrategy(ABC, BaseModel):
    model_config = standard_model_config

    _subtypes: ClassVar[dict] = {}

    def __init_subclass__(cls, **kwargs: Unpack[ConfigDict]):
        cls._subtypes[cls.type] = cls

    @abstractmethod
    def calculate(self, transactions: list['Transaction']) -> float:
        pass


class TransactionCountLiquidity(LiquidityStrategy):
    type: Literal['transaction_count'] = 'transaction_count'
    window: int | timedelta

    @property
    def window_seconds(self) -> int:
        return int(self.window.total_seconds()) if isinstance(self.window, timedelta) else self.window

    def calculate(self, transactions: list['Transaction']) -> float:
        window_start = current_timestamp().timestamp() - self.window_seconds
        count = sum(1 for tx in transactions if tx.execution_time.timestamp() >= window_start)
        return count / self.window_seconds # trades per second


class AverageIntervalLiquidity(LiquidityStrategy):
    type: Literal['average_interval'] = 'average_interval'
    amount: int

    def calculate(self, transactions: list['Transaction']) -> float:
        if len(transactions) < self.amount + 1:
            return 0.0  # Not enough data

        recent = transactions[-(self.amount + 1):]
        deltas = [
            (recent[i].execution_time - recent[i - 1].execution_time).total_seconds()
            for i in range(1, len(recent))
        ]

        avg_interval = sum(deltas) / len(deltas)
        return 1 / avg_interval if avg_interval > 0 else 0.0  # trades per second


class VolumeLiquidity(LiquidityStrategy):
    type: Literal['volume'] = 'volume'
    window: int | timedelta

    @property
    def window_seconds(self) -> int:
        return int(self.window.total_seconds()) if isinstance(self.window, timedelta) else self.window

    def calculate(self, transactions: list['Transaction']) -> float:
        window_start = current_timestamp().timestamp() - self.window_seconds
        total_volume = sum(tx.quantity for tx in transactions if tx.execution_time.timestamp() >= window_start)
        return total_volume / self.window_seconds  # volume per second


class PriceClusteringLiquidity(LiquidityStrategy):
    type: Literal['price_clustering'] = 'price_clustering'
    band_percent: float

    def calculate(self, transactions: list['Transaction']) -> float:
        if not transactions:
            return 0.0
        last_price = transactions[-1].price
        band = self.band_percent * last_price
        relevant = [tx for tx in transactions if abs(tx.price - last_price) <= band]
        return len(relevant)


class TimeSinceLastTradeLiquidity(LiquidityStrategy):
    type: Literal['time_since_last_trade'] = 'time_since_last_trade'

    def calculate(self, transactions: list['Transaction']) -> float:
        if not transactions:
            return 0.0
        delta = current_timestamp() - transactions[-1].execution_time
        return 1 / delta.total_seconds() if delta.total_seconds() > 0 else 0.0


class LiquidityCache:
    def __init__(self, strategy: LiquidityStrategy):
        self.strategy = strategy
        self._last_transaction_ids: list[uuid.UUID] = []
        self._cached_liquidity: float = 0.0

    def update(self, transactions: list['Transaction']) -> float:
        current_ids = [tx.id for tx in transactions]

        if current_ids == self._last_transaction_ids:
            return self._cached_liquidity

        self._cached_liquidity = self.strategy.calculate(transactions)
        self._last_transaction_ids = current_ids
        return self._cached_liquidity
