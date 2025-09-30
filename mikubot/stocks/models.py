from typing import TYPE_CHECKING
from typing import Any, Self, ClassVar, Callable, Annotated
from pydantic import BaseModel, Field, SerializeAsAny, PrivateAttr, field_validator, model_validator
from pydantic import NonNegativeFloat, PositiveFloat, PositiveInt, AnyUrl
from datetime import datetime, timezone, timedelta
from enum import Enum
from asyncio import sleep
import uuid

from . import metrics
from .utils import current_timestamp, next_month, standard_model_config
from .derivative_rules import DerivativeRuleConfig

if TYPE_CHECKING:
    from .core import Market


type NonEmptyString = Annotated[str, Field(min_length=1)]


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class MarketModel(BaseModel):
    model_config = standard_model_config

    _db_lookup: ClassVar[Callable[[str, str], dict]] = PrivateAttr()
    _db_store: ClassVar[Callable[[str, str, dict], None]] = PrivateAttr()


class Transaction(MarketModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: PositiveInt
    security_key: NonEmptyString
    type: TransactionType
    quantity: PositiveInt = 1
    price: NonNegativeFloat | None = None
    order_fee: NonNegativeFloat = 0.0
    limit: PositiveFloat | None = None
    stop: PositiveFloat | None = None
    creation_time: datetime = Field(default_factory=current_timestamp)
    expiration_time: datetime = Field(default_factory=next_month)
    status: TransactionStatus = TransactionStatus.PENDING
    execution_time: datetime | None = None
    cancellation_time: datetime | None = None
    cancelled_time: datetime | None = None

    @model_validator(mode="after")
    def check_buy_price(self) -> Self:
        if self.price and self.type == TransactionType.BUY and self.price <= 0:
            raise ValueError("BUY orders must have a price > 0")
        return self

    def save(self):
        domain = "pending_transactions" if self.is_pending or self.is_cancellation_requested else "archived_transactions"
        self.__class__._db_store(domain, str(self.id), self.model_dump(exclude={"id"}))

    @classmethod
    def get(cls, id_: uuid.UUID | str) -> Self | None:
        data = cls._db_lookup("pending_transactions", str(id_))

        if not data:
            data = cls._db_lookup("archived_transactions", str(id_))

        return cls(id=id_, **data) if data else None

    @property
    def is_buy(self) -> bool:
        return self.type == TransactionType.BUY

    @property
    def is_sell(self) -> bool:
        return self.type == TransactionType.SELL

    @property
    def is_pending(self) -> bool:
        return self.status == TransactionStatus.PENDING

    @property
    def is_executed(self) -> bool:
        return self.status == TransactionStatus.EXECUTED

    @property
    def is_cancelled(self) -> bool:
        return self.status == TransactionStatus.CANCELLED

    @property
    def is_cancellation_requested(self) -> bool:
        return self.status == TransactionStatus.CANCELLING

    @property
    def is_rejected(self):
        return self.status == TransactionStatus.REJECTED

    @property
    def is_expired(self) -> bool:
        return current_timestamp() >= self.expiration_time

    def request_cancellation(self):
        self.status = TransactionStatus.CANCELLING
        self.cancellation_time = current_timestamp()

    def set_cancelled(self):
        self.status = TransactionStatus.CANCELLED
        self.cancelled_time = current_timestamp()

    def set_executed(self):
        self.status = TransactionStatus.EXECUTED
        self.execution_time = current_timestamp()

    def set_rejected(self):
        self.status = TransactionStatus.REJECTED

    def should_execute(self, market: "Market", security: "Security", portfolio: "Portfolio") -> bool:
        # Check status and expiration
        if not self.is_pending or self.is_expired:
            return False

        # Apply stop/limit rules
        if self.is_buy:
            price_per_unit = security.ask

            if self.limit is not None and price_per_unit >= self.limit:
                return False  # too expensive, wait
            if self.stop is not None and price_per_unit < self.stop:
                return False  # stop price not reached yet

            check = market.can_buy(security, portfolio, self.quantity, limit=self.limit, stop=self.stop)

        else:
            price_per_unit = security.bid

            if self.limit is not None and price_per_unit <= self.limit:
                return False  # price too low, wait
            if self.stop is not None and price_per_unit > self.stop:
                return False  # stop price not triggered yet

            check = market.can_sell(security, portfolio, self.quantity, limit=self.limit, stop=self.stop)

        if not check.allowed and market.is_open and market.settings.enabled:
            # Not allowed to BUY/SELL but market was open.
            self.set_rejected()
            self.save()

        return check.allowed

    async def wait_until_execution(self, timeout: int | timedelta = 10, interval: float = 0.5):
        timeout_seconds = int(timeout.total_seconds()) if isinstance(timeout, timedelta) else timeout
        end = current_timestamp().timestamp() + timeout_seconds

        while current_timestamp().timestamp() < end:
            t = self.get(self.id)
            if t.is_executed or t.is_cancelled or t.is_rejected:
                return

            await sleep(interval)


class SecurityLinkConfig(MarketModel):
    enabled: bool = True
    remotes: list[NonEmptyString] = Field(default_factory=list)
    tickers: list[NonEmptyString] = Field(default_factory=list)
    multiplier: float = 1.0
    noise: NonNegativeFloat = 0.0

    # Duck-Typing to serialize subclass fields
    derivative_rules: list[SerializeAsAny[DerivativeRuleConfig]] = Field(default_factory=list)

    @field_validator("derivative_rules", mode="before")  # noqa
    @classmethod
    def validate_derivative_rules(cls, value: list[dict | DerivativeRuleConfig]) -> Any:
        result = []

        for item in value:
            if isinstance(item, DerivativeRuleConfig):
                result.append(item)
            elif isinstance(item, dict):
                type_key = item.get("type")
                type_cls = DerivativeRuleConfig.get_type(type_key)

                if type_cls is None:
                    raise ValueError(f"Unknown derivative rule: {type_key}")

                result.append(type_cls(**item))
            else:
                raise TypeError(f"Unsupported derivative rule definition: {item}")

        return result


class SecurityLinkState(MarketModel):
    last_synced: datetime = Field(default_factory=lambda: datetime.min.replace(tzinfo=timezone.utc))


class SecurityConfig(MarketModel):
    key: NonEmptyString
    name: NonEmptyString
    starting_price: PositiveFloat
    icon_url: AnyUrl | None = None
    base_spread: NonNegativeFloat = 0.01
    link: SecurityLinkConfig | None = None

    liquidity_strategy: SerializeAsAny[metrics.LiquidityStrategy] = Field(default_factory=lambda: metrics.TransactionCountLiquidity(window=300))
    volatility_strategy: SerializeAsAny[metrics.VolatilityStrategy] = Field(default_factory=lambda: metrics.LastNVolatility(amount=10))
    price_update_strategy: SerializeAsAny[metrics.PriceUpdateStrategy] = Field(default_factory=lambda: metrics.LastTradePriceStrategy())

    @field_validator("liquidity_strategy", mode="before")  # noqa
    @classmethod
    def validate_liquidity_strategies(cls, value: dict | metrics.LiquidityStrategy) -> Any:
        if isinstance(value, metrics.LiquidityStrategy):
            return value

        type_class = metrics.LiquidityStrategy._subtypes[value.get("type")]  # noqa
        return type_class(**value)

    @field_validator("volatility_strategy", mode="before")  # noqa
    @classmethod
    def validate_volatility_strategies(cls, value: dict | metrics.VolatilityStrategy) -> Any:
        if isinstance(value, metrics.VolatilityStrategy):
            return value

        type_class = metrics.VolatilityStrategy._subtypes[value.get("type")]  # noqa
        return type_class(**value)

    @field_validator("price_update_strategy", mode="before")  # noqa
    @classmethod
    def validate_price_update_strategies(cls, value: dict | metrics.PriceUpdateStrategy) -> Any:
        if isinstance(value, metrics.PriceUpdateStrategy):
            return value

        type_class = metrics.PriceUpdateStrategy._subtypes[value.get("type")]  # noqa
        return type_class(**value)

    @model_validator(mode="after")
    def ensure_no_self_reference(self) -> Self:
        if self.link and self.key in self.link.tickers:
            raise ValueError(f"Security '{self.key}' cannot reference itself in 'tickers'.")
        return self


class SecurityState(MarketModel):
    price: NonNegativeFloat
    frozen: bool = False
    listed: bool = True
    transactions: list[uuid.UUID] = Field(default_factory=list)
    holders: set[PositiveInt] = Field(default_factory=set)
    link: SecurityLinkState | None = None


class Security(MarketModel):
    config: SecurityConfig
    state: SecurityState

    # Runtime-only attributes
    _cached_volatility: float | None = PrivateAttr(None)
    _cached_liquidity: float | None = PrivateAttr(None)

    def save_state(self):
        self.__class__._db_store("securities", self.config.key, self.state.model_dump())

    @classmethod
    def load_state(cls, key: str) -> SecurityState | None:
        data = cls._db_lookup("securities", key)
        return SecurityState.model_validate(data) if data else None

    @property
    def ask(self) -> float:
        ask_price = self.state.price + 0.5 * self.calculate_spread()
        return round(ask_price, 2)

    @property
    def bid(self) -> float:
        bid_price = self.state.price - 0.5 * self.calculate_spread()
        return round(max(bid_price, 0.0), 2)

    def calculate_spread(self) -> float:
        volatility = self.calculate_volatility()
        liquidity = max(self.calculate_liquidity(), 1.0)

        base_spread = self.config.base_spread * self.state.price
        spread = base_spread * (1 + volatility) * (1 + (1 / (liquidity + 1e-5)))
        return max(spread, 0.001)

    def update_price(self, transaction: Transaction):
        new_price = self.config.price_update_strategy.apply(self, transaction)
        self.state.price = round(new_price, 2)

    def get_transactions(self) -> list[Transaction]:
        archived = [(id_, self.__class__._db_lookup("archived_transactions", str(id_)))
                    for id_ in self.state.transactions]

        # Only valid items
        archived = [(id_, data) for id_, data in archived if data is not None]
        return [Transaction(id=id_, **data) for id_, data in archived]

    def get_holders(self) -> list["Portfolio"]:
        items = [(id_, self.__class__._db_lookup("portfolios", str(id_)))
                 for id_ in self.state.holders]

        # Only valid items
        items = [(id_, data) for id_, data in items if data is not None]
        return [Portfolio(user_id=id_, **data) for id_, data in items if data is not None]

    def calculate_volatility(self) -> float:
        if self._cached_volatility is not None:
            return self._cached_volatility

        # Look up transactions that are executed
        executed = self.get_transactions()

        self._cached_volatility = self.config.volatility_strategy.calculate(executed)
        return self._cached_volatility

    def calculate_liquidity(self) -> float:
        if self._cached_volatility is not None:
            return self._cached_volatility

        # Look up transactions that are executed
        executed = self.get_transactions()

        self._cached_liquidity = self.config.liquidity_strategy.calculate(executed)
        return self._cached_liquidity


class Position(BaseModel):
    security_key: NonEmptyString
    quantity: PositiveFloat
    cost_basis: NonNegativeFloat  # security.price * quantity
    created_at: datetime = Field(default_factory=current_timestamp)

    @property
    def average_buy_price(self) -> float:
        return self.cost_basis / self.quantity

    def market_value(self, security_state: SecurityState) -> float:
        return self.quantity * security_state.price

    def unrealized_pnl(self, security_state: SecurityState) -> float:
        return (security_state.price - self.average_buy_price) * self.quantity

    def unrealized_pnl_change(self, security_state: SecurityState) -> float:
        if self.cost_basis < 1e-12:
            return security_state.price

        return (security_state.price - self.average_buy_price) / self.average_buy_price

class Portfolio(MarketModel):
    user_id: PositiveInt
    balance: float = 0.0
    positions: dict[NonEmptyString, Position] = Field(default_factory=dict)
    transactions: list[uuid.UUID] = Field(default_factory=list)

    @property
    def total_balance(self) -> float:
        securities_held = {k: (p, Security.load_state(k)) for k, p in self.positions.items()}
        securities_value = sum(s.price * p.quantity for p, s in securities_held.values() if s is not None)
        return self.balance + securities_value

    def save(self):
        self.__class__._db_store("portfolios", str(self.user_id), self.model_dump(exclude={"user_id"}))

    @classmethod
    def get(cls, user_id: int) -> Self | None:
        data = cls._db_lookup("portfolios", str(user_id))
        return cls(user_id=user_id, **data) if data else None

    def add_position(self, ticker: str, quantity: int, cost: float):
        position = self.positions.get(ticker)

        if position:
            position.quantity += quantity
            position.cost_basis += cost
        else:
            self.positions[ticker] = Position(
                security_key=ticker,
                quantity=quantity,
                cost_basis=cost,
            )

    def remove_position(self, ticker: str, quantity: int):
        position = self.positions.get(ticker)

        if not position or position.quantity < quantity:
            raise ValueError("Not enough holdings to remove")

        # Save old values
        original_quantity = position.quantity
        original_cost = position.cost_basis

        # Calculate what portion we're removing
        removed_fraction = quantity / original_quantity
        cost_removed = original_cost * removed_fraction

        # Update position
        position.quantity -= quantity
        position.cost_basis -= cost_removed

        if position.quantity == 0:
            del self.positions[ticker]

    def get_transactions(self) -> list[Transaction]:
        items = [(id_, self.__class__._db_lookup("archived_transactions", str(id_))) for id_ in self.transactions]
        items += [(id_, self.__class__._db_lookup("pending_transactions", str(id_))) for id_ in self.transactions]

        # Only valid items
        items = [(id_, data) for id_, data in items if data is not None]

        return [Transaction(id=id_, **data) for id_, data in items if data is not None]
