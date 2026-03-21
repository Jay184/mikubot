from typing import NamedTuple, cast, Literal
from datetime import datetime, timedelta
from loguru import logger

from ..config import StockMarketSettings
from .models import MarketModel, Portfolio, Security, SecurityState, SecurityLinkState, Transaction
from .store import MarketStore
from .history import HistoryService
from .securities import SecurityRepository
from .transactions import TransactionEngine
from .graphs import GraphService
from .utils import current_timestamp


class CheckResult(NamedTuple):
    allowed: bool
    reason: str = ""


class Market:
    def __init__(self, settings: StockMarketSettings):
        self.settings = settings

        self.store = MarketStore(settings.market_file)
        self.history = HistoryService(self.store)
        self.securities = SecurityRepository(self.store, settings)
        self.tx_engine = TransactionEngine(self, self.store, self.history)
        self.graphs = GraphService(self.history)

        MarketModel._db_lookup = self.store.lookup
        MarketModel._db_store = self.store.store

        if settings.enabled:
            self.store.initialize()

            if self.settings.market_maker_id:
                # ensure market maker and starting securities exist
                self._ensure_market_maker(self.settings.market_maker_id)
            self._ensure_starting_securities()
            self._remove_dangling_securities()

    @property
    def is_open(self) -> bool:
        now = current_timestamp().time()

        open_time = self.settings.open_time
        close_time = self.settings.close_time

        if open_time < close_time:
            # Normal same-day interval, e.g. 09:00–17:00
            return open_time <= now < close_time
        else:
            # Overnight interval, e.g. 22:00–06:00
            return now >= open_time or now < close_time

    def get_top_portfolios(self, top: int = 10) -> list[Portfolio]:
        """
        Returns a list of tuples (Portfolio, balance) sorted descending by balance.
        """
        portfolios = self.store.domain("portfolios")
        top_list = []

        for user_id, p_data in portfolios.items():
            p = Portfolio(user_id=int(user_id), **p_data)
            top_list.append(p)

        # Sort descending by balance
        top_list.sort(key=lambda x: x.total_balance, reverse=True)
        return top_list[:top]

    def set_price(self, ticker: str, new_price: float):
        sec = self.securities.get(ticker)
        sec.state.price = new_price
        sec.save_state()
        self.history.record_price(ticker, sec.state.price)
        holders = sec.get_holders()
        self.history.record_all_balances(holders)

    def apply_change(self, ticker: str, change: float):
        sec = self.securities.get(ticker)
        sec.state.price *= 1 + change
        sec.save_state()
        self.history.record_price(ticker, sec.state.price)
        holders = sec.get_holders()
        self.history.record_all_balances(holders)

    def adjust_balance(self, portfolio_id: int, amount: float) -> float:
        portfolio = Portfolio.get(portfolio_id)
        portfolio.balance = max(0.0, portfolio.balance + amount)
        portfolio.save()
        self.history.record_balance(portfolio)
        return portfolio.balance

    def set_holdings(self, portfolio_id: int, ticker: str, quantity: float, *, record: bool = True) -> float:
        portfolio = Portfolio.get(portfolio_id)
        security = self.securities.get(ticker)
        old_position = portfolio.positions.get(ticker)

        old_quantity = old_position.quantity if old_position else 0.0

        if quantity == old_quantity:
            return quantity

        elif quantity == 0:
            # Remove entirely if it exists
            if old_position:
                portfolio.remove_position(ticker, old_quantity)

            if portfolio_id in security.state.holders:
                security.state.holders.remove(portfolio_id)

        elif quantity > old_quantity:
            # Add the difference (gifted, cost = 0)
            portfolio.add_position(ticker, quantity - old_quantity, cost=security.ask)
            security.state.holders.add(portfolio_id)

        else:  # quantity < old_quantity
            # Remove the excess
            portfolio.remove_position(ticker, old_quantity - quantity)

        # Save portfolio
        portfolio.save()

        if record:
            self.history.record_balance(portfolio)

        return quantity

    def refund_position(self, portfolio_id: int, ticker: str, *, refund_mode: Literal["buy", "current"] = "buy"):
        self.set_holdings(portfolio_id, ticker, quantity=0)

        data = self.store.lookup("securities", ticker)

        if not data:
            return

        # Hand out current value
        if refund_mode == "current":
            price = data.get("price", 0.0)
            self.adjust_balance(portfolio_id, price)

        # Refund security
        elif refund_mode == "buy":
            position = Portfolio.get(portfolio_id).positions.get(ticker)
            self.adjust_balance(portfolio_id, position.cost_basis if position else 0.0)

    def can_operate(self, security: Security | None) -> CheckResult:
        if not self.settings.enabled:
            return CheckResult(False, "Market is disabled")

        if not self.is_open:
            return CheckResult(False, "Market is closed")

        if security is None:
            return CheckResult(False, "Security not found")

        if security.state.frozen:
            return CheckResult(False, f"{security.config.key} is frozen")

        return CheckResult(True)

    def can_trade(self, security: Security | None, portfolio: Portfolio, qty: float, *, limit: float | None = None, stop: float | None = None) -> CheckResult:
        can_operate = self.can_operate(security)

        if not can_operate.allowed:
            return can_operate

        if portfolio is None:
            return CheckResult(False, "Portfolio not found")

        if qty <= 0:
            return CheckResult(False, "Quantity must be positive")

        if limit is not None and limit <= 0:
            return CheckResult(False, "LIMIT must be positive")

        if stop is not None and stop <= 0:
            return CheckResult(False, "STOP must be positive")

        return CheckResult(True)

    def can_buy(self, security: Security, portfolio: Portfolio, qty: float, *, limit: float | None = None, stop: float | None = None) -> CheckResult:
        can_trade = self.can_trade(security, portfolio, qty, limit=limit, stop=stop)

        if not can_trade.allowed:
            return can_trade

        if security.state.price < 1e-12:
            return CheckResult(False, "Security is expired worthless")

        price_per_unit = max(cast(float, stop), cast(float, limit)) if (limit and stop) else (limit or stop or security.ask)
        order_fee = self.settings.order_fee + self.settings.order_fee_rate * price_per_unit
        total_cost = qty * price_per_unit + order_fee

        if portfolio.balance < total_cost:
            return CheckResult(False, "Insufficient balance")

        return CheckResult(True)

    def can_sell(self, security: Security, portfolio: Portfolio, qty: float, *, limit: float | None = None, stop: float | None = None) -> CheckResult:
        can_trade = self.can_trade(security, portfolio, qty, limit=limit, stop=stop)

        if not can_trade.allowed:
            return can_trade

        position = portfolio.positions.get(security.config.key)

        if not position or position.quantity < qty:
            return CheckResult(False, "Insufficient holdings")

        price_per_unit = max(cast(float, stop), cast(float, limit)) if (limit and stop) else (limit or stop or security.bid)
        net_proceeds = qty * price_per_unit * (1 - self.settings.order_fee_rate) - self.settings.order_fee

        if portfolio.balance + net_proceeds < 0:
            return CheckResult(False, "Insufficient funds to cover fees and losses")

        return CheckResult(True)

    def can_cancel(self, transaction_id: str, portfolio_id: int | None = None) -> CheckResult:
        if not self.is_open:
            return CheckResult(False, "Market is closed")

        data = self.store.lookup("pending_transactions", transaction_id)

        if not data:
            return CheckResult(False, "Transaction not found")

        transaction = Transaction.get(transaction_id)

        if portfolio_id is not None and transaction.user_id != portfolio_id:
            return CheckResult(False, "Transaction not found")

        if not transaction.is_pending:
            return CheckResult(False, "This transaction is not pending")

        return CheckResult(True)

    def can_sync(self, security: Security | None, *, now: datetime, interval: float, local: bool) -> CheckResult:
        can_operate = self.can_operate(security)

        if not can_operate.allowed:
            return can_operate

        link = security.config.link
        if not link or not link.enabled:
            return CheckResult(False, "No active link")

        if local and not link.tickers:
            return CheckResult(False, "Local link missing tickers")

        if not local and not link.remotes:
            return CheckResult(False, "Remote link missing remotes")

        if security.state.price < 1e-12:
            return CheckResult(False, "Security is expired worthless")

        last_sync = now - security.state.link.last_synced
        if last_sync <= timedelta(seconds=interval):
            return CheckResult(False, "Interval not yet elapsed")

        return CheckResult(True)

    @staticmethod
    def _ensure_market_maker(user_id: int):
        """Create market maker portfolio if it doesn't exist already."""
        market_maker = Portfolio.get(user_id)
        if not market_maker:
            market_maker = Portfolio(user_id=user_id)
            market_maker.save()

    def _ensure_starting_securities(self):
        """Create configured starting securities if missing in the store."""
        available = {k.upper(): v for k, v in self.store.domain("securities").items()}
        now = int(current_timestamp().timestamp())

        for security_config in self.settings.securities:
            ticker = security_config.key.upper()

            if ticker not in available:
                state = SecurityState(
                    price=security_config.starting_price,
                    link=SecurityLinkState()
                )

                self.store.store("securities", ticker, state.model_dump())
                self.history.record_price(ticker, state.price, now)

    def _remove_dangling_securities(self, refund_mode: Literal["buy", "current"] = "buy"):
        security_states = self.store.domain("securities")
        security_configs = self.settings.securities
        available_tickers = {sec.key for sec in security_configs}

        portfolios = [Portfolio(user_id=int(id_), **data) for id_, data in self.store.domain("portfolios").items()]

        for ticker, security_state in security_states.items():
            if ticker not in available_tickers:
                for portfolio in portfolios:
                    if ticker in portfolio.positions:
                        self.refund_position(portfolio.user_id, ticker, refund_mode=refund_mode)

                # Remove state
                self.store.remove("securities", ticker)

                # In case we want to remove history
                #self.store.execute("DELETE FROM price_history WHERE security_key = ?", (ticker,))

                for conf in security_configs:
                    if conf.link and ticker in conf.link.tickers:
                        logger.warning(f"[REMOVE] {ticker} still referenced in {conf.key}")

                logger.info(f"[REMOVE] {ticker} fully removed.")