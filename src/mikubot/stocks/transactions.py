from typing import TYPE_CHECKING
from loguru import logger
import asyncio
import uuid

from .models import Portfolio, Transaction, Security, TransactionType
from .history import HistoryService
from .store import MarketStore


if TYPE_CHECKING:
    from .core import Market


class TransactionEngine:
    def __init__(self, market: "Market", store: MarketStore, history: HistoryService):
        self.market = market
        self.store = store
        self.history = history

    def buy(self, portfolio: Portfolio, security: Security, quantity: float = 1.0, *, limit: float = None, stop: float = None) -> Transaction:
        check = self.market.can_buy(security, portfolio, quantity, limit=limit, stop=stop)

        if not check.allowed:
            raise ValueError(check.reason)

        buy_order = Transaction(
            user_id=portfolio.user_id,
            security_key=security.config.key,
            type=TransactionType.BUY,
            quantity=quantity,
            limit=limit,
            stop=stop,
        )
        buy_order.save()

        portfolio.transactions.append(buy_order.id)
        portfolio.save()

        return buy_order

    def sell(self, portfolio: Portfolio, security: Security, quantity: float = 1.0, *, limit: float = None, stop: float = None) -> Transaction:
        check = self.market.can_sell(security, portfolio, quantity, limit=limit, stop=stop)

        if not check.allowed:
            raise ValueError(check.reason)

        sell_order = Transaction(
            user_id=portfolio.user_id,
            security_key=security.config.key.upper(),
            type=TransactionType.SELL,
            quantity=quantity,
            limit=limit,
            stop=stop,
        )
        sell_order.save()

        portfolio.transactions.append(sell_order.id)
        portfolio.save()

        return sell_order

    def cancel(self, transaction_id: str, portfolio_id: int | None = None):
        check = self.market.can_cancel(transaction_id, portfolio_id)

        if not check.allowed:
            raise ValueError(check.reason)

        transaction = Transaction.get(transaction_id)
        transaction.request_cancellation()
        transaction.save()

    def execute(self, portfolio: Portfolio, transaction: Transaction, security: Security):
        market_maker = Portfolio.get(self.market.settings.market_maker_id) if self.market.settings.market_maker_id else None
        transaction.set_executed()

        # Set transaction fields
        execution_price = security.ask if transaction.is_buy else security.bid
        order_fee = self.market.settings.order_fee + self.market.settings.order_fee_rate * execution_price * transaction.quantity
        applied_spread = abs(execution_price - security.state.price)

        transaction.price = execution_price
        transaction.order_fee = order_fee

        # Update market maker
        if market_maker:
            market_maker.balance += order_fee + transaction.quantity * applied_spread
            market_maker.save()  # TODO Logic will fail if `portfolio` is the Market Maker.

        if transaction.is_buy:
            portfolio.balance -= transaction.quantity * execution_price + order_fee
            portfolio.add_position(security.config.key, transaction.quantity, transaction.quantity * execution_price)
            security.state.holders.add(portfolio.user_id)

        elif transaction.is_sell:
            portfolio.balance += transaction.quantity * execution_price
            portfolio.balance -= order_fee
            portfolio.remove_position(security.config.key, transaction.quantity)

            position = portfolio.positions.get(security.config.key)
            if not position and portfolio.user_id in security.state.holders:
                security.state.holders.remove(portfolio.user_id)

        security.state.transactions.append(transaction.id)
        security.update_price(transaction)

        security.save_state()
        portfolio.save()
        transaction.save()

        execution_timestamp = int(transaction.execution_time.timestamp())

        # Record changes for graphs
        self.history.record_price(security.config.key, security.state.price, execution_timestamp)

        for portfolio in security.get_holders():
            self.history.record_balance(portfolio, execution_timestamp)

    async def executor_loop(self, interval: float = 1.0):
        while True:
            # Don't operate when closed
            if not self.market.is_open:
                await asyncio.sleep(30.0)
                continue

            pending_data = self.store.domain("pending_transactions")
            pending = (Transaction(id=uuid.UUID(key), **data) for key, data in pending_data.items())

            for tx in pending:
                security = self.market.securities.get(tx.security_key)
                portfolio = Portfolio.get(tx.user_id)

                try:
                    if tx.is_cancellation_requested:
                        self.remove_pending_transaction(tx)
                        tx.set_cancelled()
                        portfolio.transactions.append(tx.id)

                        tx.save()
                        portfolio.save()
                        logger.info(f"Transaction cancelled: {tx.id}")

                    elif tx.should_execute(self.market, security, portfolio):
                        self.remove_pending_transaction(tx)
                        self.execute(portfolio, tx, security)
                        logger.info(f"Transaction executed: {tx.id}")

                    elif tx.is_expired:
                        self.remove_pending_transaction(tx)
                        tx.set_rejected()
                        tx.save()
                        logger.info(f"Transaction rejected: {tx.id}, reason: Expired")
                except Exception as e:
                    logger.error(f"Error processing transaction {tx.id}")
                    logger.exception(e)

            await asyncio.sleep(interval)

    def remove_pending_transaction(self, transaction: Transaction):
        self.store.remove("pending_transactions", str(transaction.id))

    def get_pending_transactions(self) -> list[Transaction]:
        pending_data = self.store.domain("pending_transactions")
        return [Transaction(id=uuid.UUID(key), **data) for key, data in pending_data.items()]
