from typing import TYPE_CHECKING
from typing import ClassVar, Unpack
from abc import ABC, abstractmethod
from pydantic import BaseModel, ConfigDict


if TYPE_CHECKING:
    from ..models import Security
    from ..core import Market

from ..utils import standard_model_config


class KnockoutException(Exception):
    """Raised when a security hits a knockout condition and should stop updating."""
    pass


class DerivativeRuleBaseModel(BaseModel):
    model_config = standard_model_config


class DerivativeRule(ABC, DerivativeRuleBaseModel):
    @abstractmethod
    def apply(self, security: "Security", change: float, interval: float) -> float:
        ...


class DerivativeRuleConfig(ABC, DerivativeRuleBaseModel):
    # Registry of all subclasses by type string
    _subtypes: ClassVar[dict[str, type["DerivativeRuleConfig"]]] = {}

    def __init_subclass__(cls, **kwargs: Unpack[ConfigDict]):
        super().__init_subclass__(**kwargs)

        pydantic_fields = getattr(cls, "__pydantic_fields__", {})

        if "type" in pydantic_fields:
            function_type = pydantic_fields["type"].default
            DerivativeRuleConfig._subtypes[function_type] = cls

    @staticmethod
    def get_type(type_key: str) -> type["DerivativeRuleConfig"] | None:
        return DerivativeRuleConfig._subtypes.get(type_key)

    @abstractmethod
    def create(self, market: "Market", security: "Security") -> DerivativeRule | None:
        ...
