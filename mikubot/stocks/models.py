from typing import Any, Self, ClassVar, Callable
from pydantic import BaseModel, Field, SerializeAsAny, PrivateAttr, field_validator
from datetime import datetime, timedelta
from enum import Enum
from asyncio import sleep
import uuid

from . import metrics
from .utils import current_timestamp, next_month, standard_model_config


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLING = 'CANCELLING'
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class MarketModel(BaseModel):
    model_config = standard_model_config

    _db_lookup: ClassVar[Callable[[str, str], dict]] = PrivateAttr()
    _db_store: ClassVar[Callable[[str, str, dict], None]] = PrivateAttr()


class Transaction(MarketModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: int
    security_key: str
    type: TransactionType
    quantity: int = 1
    price: float | None = None
    order_fee: float = 0.0
    limit: float | None = None
    stop: float | None = None
    creation_time: datetime = Field(default_factory=current_timestamp)
    expiration_time: datetime = Field(default_factory=next_month)
    status: TransactionStatus = TransactionStatus.PENDING
    execution_time: datetime | None = None
    cancellation_time: datetime | None = None
    cancelled_time: datetime | None = None

    def save(self):
        domain = 'pending_transactions' if self.is_pending or self.is_cancellation_requested else 'archived_transactions'
        self.__class__._db_store(domain, str(self.id), self.model_dump(exclude={'id'}))

    @classmethod
    def get(cls, id_: uuid.UUID | str) -> Self | None:
        data = cls._db_lookup('pending_transactions', str(id_))

        if not data:
            data = cls._db_lookup('archived_transactions', str(id_))

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

    def should_execute(self, security: 'Security', portfolio: 'Portfolio') -> bool:
        # Check status and expiration
        if not self.is_pending or self.is_expired:
            return False

        # Apply stop/limit rules
        if self.is_buy:
            market_price = security.ask
            can_afford = portfolio.balance >= self.quantity * market_price

            if self.limit is not None and market_price >= self.limit:
                return False  # too expensive, wait
            if self.stop is not None and market_price < self.stop:
                return False  # stop price not reached yet
            if not can_afford:
                return False

        elif self.is_sell:
            market_price = security.bid
            has_holdings = security.key in portfolio.positions and portfolio.positions[security.key].quantity >= self.quantity

            if self.limit is not None and market_price <= self.limit:
                return False  # price too low, wait
            if self.stop is not None and market_price > self.stop:
                return False  # stop price not triggered yet
            if not has_holdings:
                return False

        return True

    async def wait_until_execution(self, timeout: int | timedelta = 10, interval: float = 0.5):
        timeout_seconds = int(timeout.total_seconds()) if isinstance(timeout, timedelta) else timeout
        end = current_timestamp().timestamp() + timeout_seconds

        while current_timestamp().timestamp() < end:
            t = self.get(self.id)
            if t.is_executed or t.is_cancelled or t.is_rejected:
                return

            await sleep(interval)


class Security(MarketModel):
    key: str
    name: str
    icon_url: str | None = None
    price: float
    base_spread: float = 0.01
    transactions: list[uuid.UUID] = []
    holders: list[int] = []

    liquidity_strategy: SerializeAsAny[metrics.LiquidityStrategy]
    volatility_strategy: SerializeAsAny[metrics.VolatilityStrategy]
    price_update_strategy: SerializeAsAny[metrics.PriceUpdateStrategy]

    # Runtime-only attributes
    _cached_volatility: float | None = PrivateAttr(None)
    _cached_liquidity: float | None = PrivateAttr(None)

    def save(self):
        self.__class__._db_store('securities', self.key, self.model_dump(exclude={'key'}))

    @classmethod
    def get(cls, key: str) -> Self | None:
        data = cls._db_lookup('securities', key)
        return cls(key=key, **data) if data else None

    @property
    def ask(self) -> float:
        ask_price = self.price + 0.5 * self.calculate_spread()
        return round(ask_price, 2)

    @property
    def bid(self) -> float:
        bid_price = self.price - 0.5 * self.calculate_spread()
        return round(max(bid_price, 0.0), 2)

    @field_validator('liquidity_strategy', mode='before')  # noqa
    @classmethod
    def validate_liquidity_strategies(cls, value: dict | metrics.LiquidityStrategy) -> Any:
        if isinstance(value, metrics.LiquidityStrategy):
            return value

        type_class = metrics.LiquidityStrategy._subtypes[value.get('type')]  # noqa
        return type_class(**value)

    @field_validator('volatility_strategy', mode='before')  # noqa
    @classmethod
    def validate_volatility_strategies(cls, value: dict | metrics.VolatilityStrategy) -> Any:
        if isinstance(value, metrics.VolatilityStrategy):
            return value

        type_class = metrics.VolatilityStrategy._subtypes[value.get('type')]  # noqa
        return type_class(**value)

    @field_validator('price_update_strategy', mode='before')  # noqa
    @classmethod
    def validate_price_update_strategies(cls, value: dict | metrics.PriceUpdateStrategy) -> Any:
        if isinstance(value, metrics.PriceUpdateStrategy):
            return value

        type_class = metrics.PriceUpdateStrategy._subtypes[value.get('type')]  # noqa
        return type_class(**value)

    def get_transactions(self) -> list[Transaction]:
        archived = [(id_, self.__class__._db_lookup('archived_transactions', str(id_))) for id_ in self.transactions]

        # Only valid items
        archived = [(id_, data) for id_, data in archived if data is not None]

        return [Transaction(id=id_, **data) for id_, data in archived]

    def get_holders(self) -> list["Portfolio"]:
        items = [(id_, self.__class__._db_lookup('portfolios', str(id_))) for id_ in self.holders]

        # Only valid items
        items = [(id_, data) for id_, data in items if data is not None]

        return [Portfolio(user_id=id_, **data) for id_, data in items if data is not None]

    def calculate_volatility(self) -> float:
        if self._cached_volatility is not None:
            return self._cached_volatility

        # Look up transactions that are executed
        executed = self.get_transactions()

        self._cached_volatility = self.volatility_strategy.calculate(executed)
        return self._cached_volatility

    def calculate_liquidity(self) -> float:
        if self._cached_volatility is not None:
            return self._cached_volatility

        # Look up transactions that are executed
        executed = self.get_transactions()

        self._cached_liquidity = self.liquidity_strategy.calculate(executed)
        return self._cached_liquidity

    def update_price(self, transaction: Transaction):
        new_price = self.price_update_strategy.apply(self, transaction)
        self.price = round(new_price, 2)

    def calculate_spread(self) -> float:
        volatility = self.calculate_volatility()
        liquidity = max(self.calculate_liquidity(), 1.0)

        # Simplified spread formula
        base_spread = self.base_spread * self.price
        spread = base_spread * (1 + volatility) * (1 + (1 / (liquidity + 1e-5)))
        return max(spread, 0.001)


class Position(BaseModel):
    security_key: str
    quantity: int
    cost_basis: float  # security.price * quantity
    created_at: datetime = Field(default_factory=current_timestamp)

    @property
    def average_buy_price(self):
        return self.cost_basis / self.quantity

    def market_value(self, security: Security) -> float:
        return self.quantity * security.price

    def unrealized_pnl(self, security: Security) -> float:
        return (security.price - self.average_buy_price) * self.quantity


class Portfolio(MarketModel):
    user_id: int
    balance: float = 0.0
    positions: dict[str, Position] = {}
    transactions: list[uuid.UUID] = []

    @property
    def total_balance(self) -> float:
        securities_held = {k: (p, Security.get(k)) for k, p in self.positions.items()}
        securities_value = sum(s.price * p.quantity for p, s in securities_held.values() if s is not None)
        return self.balance + securities_value

    def save(self):
        self.__class__._db_store('portfolios', str(self.user_id), self.model_dump(exclude={'user_id'}))

    @classmethod
    def get(cls, user_id: int) -> Self | None:
        data = cls._db_lookup('portfolios', str(user_id))
        return cls(user_id=user_id, **data) if data else None

    def add_position(self, security: Security, quantity: int, cost: float):
        position = self.positions.get(security.key)

        if position:
            position.quantity += quantity
            position.cost_basis += cost
        else:
            self.positions[security.key] = Position(
                security_key=security.key,
                quantity=quantity,
                cost_basis=cost,
            )

    def remove_position(self, security: Security, quantity: int):
        position = self.positions.get(security.key)

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
            del self.positions[security.key]

    def get_transactions(self) -> list[Transaction]:
        items = [(id_, self.__class__._db_lookup('archived_transactions', str(id_))) for id_ in self.transactions]
        items += [(id_, self.__class__._db_lookup('pending_transactions', str(id_))) for id_ in self.transactions]

        # Only valid items
        items = [(id_, data) for id_, data in items if data is not None]

        return [Transaction(id=id_, **data) for id_, data in items if data is not None]
