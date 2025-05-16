from typing import TYPE_CHECKING, Literal, Unpack, ClassVar
from abc import ABC, abstractmethod
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from .. import Security, Transaction

from ..utils import standard_model_config


class PriceUpdateStrategy(ABC, BaseModel):
    model_config = standard_model_config

    _subtypes: ClassVar[dict] = {}

    def __init_subclass__(cls, **kwargs: Unpack[ConfigDict]):
        cls._subtypes[cls.type] = cls

    @abstractmethod
    def apply(self, security: 'Security', transaction: 'Transaction') -> float:
        return security.price


class LastTradePriceStrategy(PriceUpdateStrategy):
    type: Literal['last_trade_price'] = 'last_trade_price'

    def apply(self, security: 'Security', transaction: 'Transaction') -> float:
        return transaction.price


class VolumeWeightedAverageStrategy(PriceUpdateStrategy):
    type: Literal['volume_weighted_average'] = 'volume_weighted_average'
    lookback: int = 10

    def apply(self, security: 'Security', transaction: 'Transaction') -> float:
        recent = security.get_transactions()[-self.lookback:]
        total_volume = transaction.quantity + sum(t.quantity for t in recent)
        weighted_sum = transaction.price * transaction.quantity + sum(
            t.price * t.quantity for t in recent
        )
        return weighted_sum / total_volume if total_volume > 0 else security.price


class SlippagePriceStrategy(PriceUpdateStrategy):
    type: Literal['slippage_price'] = 'slippage_price'
    base_impact: float = 0.01

    def apply(self, security: 'Security', transaction: 'Transaction') -> float:
        direction = 1 if transaction.price > security.price else -1
        return security.price + direction * self.base_impact * transaction.quantity
