from typing import TYPE_CHECKING
from typing import Literal
from pydantic import PositiveFloat

from .base import DerivativeRuleBaseModel, DerivativeRule, DerivativeRuleConfig

if TYPE_CHECKING:
    from .base import Market, Security


class AsymmetricBase(DerivativeRuleBaseModel):
    type: Literal["asymmetric"] = "asymmetric"
    up_factor: PositiveFloat = 1.0
    down_factor: PositiveFloat = 1.0


class AsymmetricDerivativeRule(AsymmetricBase, DerivativeRule):
    def apply(self, security: "Security", change: float, interval: float) -> float:
        if change >= 0:
            return change * self.up_factor
        else:
            return change * self.down_factor


class AsymmetricDerivativeRuleConfig(AsymmetricBase, DerivativeRuleConfig):
    def create(self, market: "Market", security: "Security") -> AsymmetricDerivativeRule | None:
        return AsymmetricDerivativeRule(
            up_factor=self.up_factor,
            down_factor=self.down_factor,
        )
