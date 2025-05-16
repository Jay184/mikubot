from datetime import datetime, timezone
from loguru import logger
from sqlitedict import SqliteDict, SqliteMultithread
from pandas import DataFrame, date_range, concat
from matplotlib import pyplot, dates
import uuid
import asyncio

from .models import MarketModel, Portfolio, Security, Transaction, TransactionType
from .utils import current_timestamp
from .intervals import IntervalData

from ..config import StockMarketSettings


GraphDataItem = tuple[datetime, float]
GraphData = list[GraphDataItem]


class Market:
    def __init__(self, settings: StockMarketSettings):
        MarketModel._db_lookup = self.lookup
        MarketModel._db_store = self.store

        self.settings = settings

        if settings.enabled:
            self.create_price_history_table()
            self.create_balance_history_table()
            self.create_starting_securities()

            # Create market maker portfolio if it doesn't exist already
            market_maker = Portfolio.get(settings.market_maker_id)
            if not market_maker:
                market_maker = Portfolio(user_id=settings.market_maker_id)
                market_maker.save()

    @property
    def is_open(self) -> bool:
        current_time = current_timestamp().time()
        return self.settings.open_time <= current_time < self.settings.close_time

    def create_starting_securities(self):
        ts = int(current_timestamp().timestamp())

        for security in self.settings.starting_securities:
            # Force upper case keys
            security.key = security.key.upper()

            if security.key not in self.domain('securities').keys():
                self.record_price(security, ts)
                security.save()

    def create_price_history_table(self):
        conn = SqliteMultithread(self.settings.market_file, False, True, False)

        conn.execute(
            """
                CREATE TABLE IF NOT EXISTS price_history (
                    security_key TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,  -- Unix timestamp in seconds
                    price REAL NOT NULL,
                    PRIMARY KEY (security_key, timestamp),
                    FOREIGN KEY (security_key) REFERENCES securities(key)
                );
            """
        )

        conn.close()

    def create_balance_history_table(self):
        conn = SqliteMultithread(self.settings.market_file, False, True, False)

        conn.execute(
            """
                CREATE TABLE IF NOT EXISTS balance_history (
                    user_id TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,  -- Unix timestamp in seconds
                    balance REAL NOT NULL,
                    PRIMARY KEY (user_id, timestamp),
                    FOREIGN KEY (user_id) REFERENCES portfolios(key)
                );
            """
        )

        conn.close()

    def record_price(self, security: Security, timestamp: int):
        conn = SqliteMultithread(self.settings.market_file, False, True, False)

        timestamp = timestamp or current_timestamp()

        conn.execute(
            """
            INSERT OR IGNORE INTO price_history (security_key, timestamp, price)
            VALUES (?, ?, ?)
            """,
            (security.key, timestamp, security.price)
        )

        conn.commit()
        conn.close()

    def record_balance(self, portfolio: Portfolio, timestamp: int = None):
        conn = SqliteMultithread(self.settings.market_file, False, True, False)

        timestamp = timestamp or current_timestamp()

        conn.execute(
            """
            INSERT OR IGNORE INTO balance_history (user_id, timestamp, balance)
            VALUES (?, ?, ?)
            """,
            (portfolio.user_id, timestamp, portfolio.total_balance)
        )

        conn.commit()
        conn.close()

    def lookup(self, domain: str, key: str) -> dict | None:
        with SqliteDict(self.settings.market_file, domain) as db:
            return db.get(key)

    def domain(self, domain: str) -> dict[str, dict]:
        with SqliteDict(self.settings.market_file, domain) as db:
            return {k: v for k, v in db.items()}

    def remove(self, domain: str, key: str) -> bool:
        with SqliteDict(self.settings.market_file, domain) as db:
            if key in db:
                del db[key]
                db.commit()
                return True

        return False

    def store(self, domain: str, key: str, value: dict):
        with SqliteDict(self.settings.market_file, domain) as db:
            db[key] = value
            db.commit()

    def remove_pending_transaction(self, transaction: Transaction):
        self.remove('pending_transactions', str(transaction.id))

    def get_pending_transactions(self) -> list[Transaction]:
        return [Transaction(id=uuid.UUID(key), **data) for key, data in self.domain('pending_transactions').items()]

    def execute_transaction(self, portfolio: Portfolio, transaction: Transaction, security: Security):
        market_maker = Portfolio.get(self.settings.market_maker_id)
        transaction.set_executed()

        # Set transaction fields
        transaction.price = security.ask if transaction.is_buy else security.bid
        transaction.order_fee = self.settings.order_fee + self.settings.order_fee_rate * transaction.price

        market_maker.balance += transaction.order_fee + transaction.quantity * abs(transaction.price - security.price)
        market_maker.save()  # Logic will fail if `portfolio` is the Market Maker.

        total_volume = transaction.quantity * transaction.price

        if transaction.is_buy:
            portfolio.balance -= total_volume
            portfolio.add_position(security, transaction.quantity, total_volume)

        elif transaction.is_sell:
            portfolio.balance += total_volume
            portfolio.remove_position(security, transaction.quantity)

        portfolio.balance -= transaction.order_fee

        security.transactions.append(transaction.id)
        security.update_price(transaction)

        portfolio.save()
        security.save()
        transaction.save()

        execution_timestamp = int(transaction.execution_time.timestamp())

        # Record changes for graphs
        self.record_price(security, execution_timestamp)

        for portfolio in security.get_holders():
            self.record_balance(portfolio, execution_timestamp)

    async def transaction_executor_loop(self, interval: float = 1.0):
        while True:
            # Don't operate when closed
            if not self.is_open:
                await asyncio.sleep(30.0)

            pending = self.get_pending_transactions()

            for transaction in pending:
                security = Security.get(transaction.security_key)
                portfolio = Portfolio.get(transaction.user_id)

                try:
                    if transaction.should_execute(security, portfolio):
                        self.remove_pending_transaction(transaction)
                        self.execute_transaction(portfolio, transaction, security)
                        logger.info(f'Transaction executed: {transaction.id}')

                    elif transaction.is_expired:
                        self.remove_pending_transaction(transaction)
                        transaction.set_rejected()
                        transaction.save()
                        logger.info(f'Transaction rejected: {transaction.id}, reason: Expired')

                    elif transaction.is_cancellation_requested:
                        self.remove_pending_transaction(transaction)
                        transaction.set_cancelled()
                        portfolio.transactions.append(transaction.id)

                        transaction.save()
                        portfolio.save()
                        logger.info(f'Transaction cancelled: {transaction.id}')

                except Exception as e:
                   logger.error(f"Error processing transaction {transaction.id}: {e}")

            await asyncio.sleep(interval)

    def buy(self, portfolio: Portfolio, security: Security, quantity: int = 1, *, limit: float = None, stop: float = None) -> Transaction:
        if not self.is_open:
            raise ValueError('Market is closed.')

        can_afford = portfolio.balance >= quantity * security.ask

        if not can_afford:
            raise ValueError('Not enough balance to buy.')

        buy_order = Transaction(
            user_id=portfolio.user_id,
            security_key=security.key,
            type=TransactionType.BUY,
            quantity=quantity,
            limit=limit,
            stop=stop,
        )
        buy_order.save()

        portfolio.transactions.append(buy_order.id)
        portfolio.save()

        return buy_order

    def sell(self, portfolio: Portfolio, security: Security, quantity: int = 1, *, limit: float = None, stop: float = None) -> Transaction:
        if not self.is_open:
            raise ValueError('Market is closed.')

        has_holdings = security.key in portfolio.positions and portfolio.positions[
            security.key].quantity >= quantity

        if not has_holdings:
            raise ValueError('Does not own enough holdings.')

        sell_order = Transaction(
            user_id=portfolio.user_id,
            security_key=security.key,
            type=TransactionType.SELL,
            quantity=quantity,
            limit=limit,
            stop=stop,
        )
        sell_order.save()

        portfolio.transactions.append(sell_order.id)
        portfolio.save()

        return sell_order

    def cancel(self, transaction_id: str):
        data = self.lookup('pending_transactions', transaction_id)

        if not data:
            raise ValueError('No such transaction.')

        transaction = Transaction(id=uuid.UUID(transaction_id), **data)

        if not transaction.is_pending:
            raise ValueError('This transaction is no longer pending and cannot be cancelled.')

        transaction.request_cancellation()
        transaction.save()

    def get_price_history(self, key: str, *, before: datetime = None, after: datetime = None, limit: int = None) -> list[tuple[datetime, float]]:
        conn = SqliteMultithread(self.settings.market_file, False, True, False)

        query_parts = []
        params = [key]

        if before:
            query_parts.append("timestamp < ?")
            params.append(int(before.timestamp()))

        if after:
            query_parts.append("timestamp > ?")
            params.append(int(after.timestamp()))

        sql = f"""\
            SELECT timestamp, price FROM price_history
            WHERE security_key = ? AND {' AND '.join(query_parts)}
            ORDER BY timestamp ASC
        """

        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        generator = conn.select(sql, params)

        return list((datetime.fromtimestamp(ts, timezone.utc), p) for ts, p in generator)

    def get_price_graph_data(self, key: str, interval: IntervalData) -> GraphData:
        data = self.get_price_history(key,
            before=interval.start,
            limit=1,
        )

        data += self.get_price_history(key,
            before=interval.end,
            after=interval.start,
        )

        return data

    def get_balance_history(self, user_id: int, *, before: datetime = None, after: datetime = None, limit: int = None) -> list[tuple[datetime, float]]:
        conn = SqliteMultithread(self.settings.market_file, False, True, False)

        query_parts = []
        params = [str(user_id)]

        if before:
            query_parts.append("timestamp < ?")
            params.append(int(before.timestamp()))

        if after:
            query_parts.append("timestamp > ?")
            params.append(int(after.timestamp()))

        sql = f"""\
            SELECT timestamp, balance FROM balance_history
            WHERE user_id = ? AND {' AND '.join(query_parts)}
            ORDER BY timestamp ASC
        """

        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        generator = conn.select(sql, params)

        return list((datetime.fromtimestamp(ts, timezone.utc), p) for ts, p in generator)

    def get_balance_graph_data(self, user_id: int, interval: IntervalData) -> GraphData:
        data = self.get_balance_history(user_id,
            before=interval.start,
            limit=1,
        )

        data += self.get_balance_history(user_id,
            before=interval.end,
            after=interval.start,
        )

        return data

    def create_graph(self, data: GraphData, interval: IntervalData) -> tuple[pyplot.Figure, pyplot.Axes]:
        fig, ax = pyplot.subplots(figsize=(12, 6))

        if len(data):
            frame = self._prepare_graph_data(data, interval)
            self._set_graph_axes(ax, frame, interval)
        else:
            self._set_empty_graph_axes(ax)

        fig.tight_layout()
        return fig, ax

    def create_graph_matrix(self, *data: GraphData, interval: IntervalData, cols: int = 3) -> tuple[pyplot.Figure, list[pyplot.Axes]]:
        rows = len(data) // cols + (1 if len(data) % cols != 0 else 0)
        fig, axes = pyplot.subplots(rows, cols, figsize=(6 * cols, 3 * rows))

        # Fix the inconsistent return types
        axes = [axes] if isinstance(axes, pyplot.Axes) else axes.flatten()

        for ax, ax_data in zip(axes, data):
            if len(ax_data):
                frame = self._prepare_graph_data(ax_data, interval)
                self._set_graph_axes(ax, frame, interval)
            else:
                self._set_empty_graph_axes(ax)

        for i in range(len(data), len(axes)):
            fig.delaxes(axes[i])

        fig.tight_layout()
        return fig, axes[:len(data)]

    @staticmethod
    def _set_graph_axes(ax: pyplot.Axes, frame: DataFrame, interval: IntervalData):
        ax.plot(frame.index, frame["price"], marker=",", linestyle="-", drawstyle="steps-post")

        # Annotate last point
        last_point = frame.iloc[-1]
        ax.annotate(f"{last_point['price']:,.2f}",
                    xy=(last_point.name, last_point['price']),
                    xytext=(15, 0),
                    textcoords="offset points",
                    ha='left', va='center',
                    bbox=dict(boxstyle="round", fc="w"))

        ax.xaxis.set_major_locator(interval.locator)
        ax.xaxis.set_major_formatter(dates.DateFormatter(interval.tick_format))
        ax.set_xlim([interval.start - interval.margin, interval.end + interval.margin])

        # ax.set_xlabel("Time")
        ax.set_ylabel("Price")
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, linestyle="--", alpha=0.5)
        # ax.axvspan(interval.start - interval.margin, df.index.min(), color="lightgrey", alpha=0.3)

    @staticmethod
    def _set_empty_graph_axes(ax: pyplot.Axes):
        ax.text(0.5, 0.5, "No data", ha='center', va='center', fontsize=12)
        ax.tick_params(
            axis='both',
            which='both',
            bottom=False,
            left=False,
            labelbottom=False,
            labelleft=False,
        )

    @staticmethod
    def _prepare_graph_data(data: GraphData, interval: IntervalData) -> DataFrame:
        # Create DataFrame
        frame = DataFrame(data, columns=["datetime", "price"])
        frame.set_index("datetime", inplace=True)
        # frame.index = to_datetime(frame.index)

        # Get the last known price before start
        last_before_start = frame[frame.index < interval.start].iloc[-1:]  # could be empty
        frame = concat([last_before_start, frame[frame.index >= interval.start]])

        # Create a full DateTimeIndex at the desired frequency
        full_index = date_range(start=interval.start, end=interval.end, freq=interval.freq)

        # Reindex and forward-fill
        # frame = frame.resample(freq).mean()
        frame = frame.reindex(full_index, method="ffill")
        frame = frame[~frame['price'].duplicated()]
        # frame.sort_index(inplace=True)

        # Ensure emd time is included
        if frame.index[-1] < interval.end:
            frame.loc[interval.end] = data[-1][1]
            frame = frame.sort_index()

        return frame
