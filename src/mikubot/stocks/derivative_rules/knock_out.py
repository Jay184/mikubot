from typing import TYPE_CHECKING
from typing import Literal
from pydantic import NonNegativeFloat

from .base import DerivativeRuleBaseModel, DerivativeRule, DerivativeRuleConfig, KnockoutException

if TYPE_CHECKING:
    from .base import Market, Security


class KnockoutBase(DerivativeRuleBaseModel):
    type: Literal["knockout"] = "knockout"
    threshold: NonNegativeFloat = 0.0


class KnockoutDerivativeRule(KnockoutBase, DerivativeRule):
    def apply(self, security: "Security", change: float, interval: float) -> float:
        projected_price = security.state.price * (1 + change)

        if projected_price <= self.threshold:
            raise KnockoutException(f"{security.config.key} knocked out at {projected_price:.2f}")

        return change

    def is_active(self, price: float) -> bool:
        return price > self.threshold


class KnockoutDerivativeRuleConfig(KnockoutBase, DerivativeRuleConfig):
    def create(self, market: "Market", security: "Security") -> KnockoutDerivativeRule | None:
        return KnockoutDerivativeRule(
            threshold=self.threshold,
        )
