from typing import TYPE_CHECKING
from typing import Literal, Self
from pydantic import NonNegativeFloat, model_validator

from .base import DerivativeRuleBaseModel, DerivativeRule, DerivativeRuleConfig

if TYPE_CHECKING:
    from .base import Market, Security


class DecayBase(DerivativeRuleBaseModel):
    type: Literal["decay"] = "decay"
    per_second: NonNegativeFloat = 0.0
    per_minute: NonNegativeFloat = 0.0
    per_hour: NonNegativeFloat = 0.0

    @model_validator(mode="after")
    def ensure_positive_rate(self) -> Self:
        if not any(k > 0 for k in (self.per_second, self.per_minute, self.per_hour)):
            raise ValueError("At least one decay rate must be positive")
        return self


class DecayDerivativeRule(DecayBase, DerivativeRule):
    def apply(self, security: "Security", change: float, interval: float) -> float:
        per_second_total = self.per_second
        per_second_total += self.per_minute / 60
        per_second_total += self.per_hour / 3600

        factor = (1.0 - per_second_total) ** interval
        return change * factor


class DecayDerivativeRuleConfig(DecayBase, DerivativeRuleConfig):
    def create(self, market: "Market", security: "Security") -> DecayDerivativeRule | None:
        return DecayDerivativeRule(
            per_second=self.per_second,
            per_minute=self.per_minute,
            per_hour=self.per_hour,
        )
