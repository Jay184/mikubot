from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from pydantic import BaseModel


if TYPE_CHECKING:
    from ..models import Security
    from ..core import Market

from ..utils import standard_model_config
from ..polymorphic import PolymorphicBase


class KnockoutException(Exception):
    """Raised when a security hits a knockout condition and should stop updating."""
    pass


class DerivativeRuleBaseModel(BaseModel):
    model_config = standard_model_config


class DerivativeRule(ABC, DerivativeRuleBaseModel):
    @abstractmethod
    def apply(self, security: "Security", change: float, interval: float) -> float:
        ...


class DerivativeRuleConfig(PolymorphicBase, ABC, identity="derivatives"):
    @abstractmethod
    def create(self, market: "Market", security: "Security") -> DerivativeRule | None:
        ...
