from datetime import datetime, timezone

from .intervals import SecurityIntervals
from .models import Portfolio
from .store import MarketStore


class HistoryService:
    def __init__(self, store: MarketStore):
        self.store = store

    def record_price(self, ticker: str, price: float, ts: int | datetime | None = None) -> None:
        ts_int = self._to_ts(ts)
        sql = "INSERT OR IGNORE INTO price_history (security_key, timestamp, price) VALUES (?, ?, ?)"
        self.store.execute(sql, (ticker, ts_int, price))

    def record_balance(self, portfolio: Portfolio, ts: int | datetime | None = None) -> None:
        ts_int = self._to_ts(ts)
        sql = "INSERT OR IGNORE INTO balance_history (user_id, timestamp, balance) VALUES (?, ?, ?)"
        self.store.execute(sql, (str(portfolio.user_id), ts_int, portfolio.total_balance))

    def record_all_balances(self, portfolios: list[Portfolio], ts: int | datetime | None = None) -> None:
        ts_int = self._to_ts(ts)
        rows = [(str(p.user_id), ts_int, p.total_balance) for p in portfolios]
        sql = "INSERT OR IGNORE INTO balance_history (user_id, timestamp, balance) VALUES (?, ?, ?)"
        self.store.executemany(sql, rows)

    def get_price_history(self, ticker: str, *, before: datetime = None, after: datetime = None, limit: int = None) -> list[tuple[datetime, float]]:
        where_clauses = ["security_key = ?"]
        params = [ticker]

        if before:
            where_clauses.append("timestamp < ?")
            params.append(int(before.timestamp()))

        if after:
            where_clauses.append("timestamp > ?")
            params.append(int(after.timestamp()))

        where_sql = " AND ".join(where_clauses)
        sql = f"SELECT timestamp, price FROM price_history WHERE {where_sql} ORDER BY timestamp ASC"

        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self.store.select(sql, tuple(params))
        return list((datetime.fromtimestamp(ts, timezone.utc), p) for ts, p in rows)

    def get_balance_history(self, user_id: int, *, before: datetime = None, after: datetime = None, limit: int = None) -> list[tuple[datetime, float]]:
        where_clauses = ["user_id = ?"]
        params = [str(user_id)]

        if before:
            where_clauses.append("timestamp < ?")
            params.append(int(before.timestamp()))

        if after:
            where_clauses.append("timestamp > ?")
            params.append(int(after.timestamp()))

        where_sql = " AND ".join(where_clauses)
        sql = f"SELECT timestamp, balance FROM balance_history WHERE {where_sql} ORDER BY timestamp ASC"

        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self.store.select(sql, tuple(params))
        return list((datetime.fromtimestamp(ts, timezone.utc), bal) for ts, bal in rows)

    def get_price_at_or_before(self, ticker: str, ts: int | datetime | None = None) -> float | None:
        cutoff = self._to_ts(ts)
        sql = """
            SELECT price FROM price_history
            WHERE security_key = ? AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
        """

        rows = self.store.select(sql, (ticker, cutoff))
        return rows[0][0] if rows else None

    def get_price_at_or_after(self, ticker: str, ts: int | datetime | None = None) -> float | None:
        cutoff = self._to_ts(ts)
        sql = """
            SELECT price FROM price_history
            WHERE security_key = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT 1
        """
        rows = self.store.select(sql, (ticker, cutoff))
        return rows[0][0] if rows else None

    def get_latest_price(self, ticker: str) -> float | None:
        return self.get_price_at_or_after(ticker)

    def get_price_at_or_before_interval(self, ticker: str, interval: SecurityIntervals) -> float | None:
        # Map interval → seconds
        interval_map = {
            SecurityIntervals.day: 86400,  # 24h
            SecurityIntervals.week: 604800,  # 7d
            SecurityIntervals.month: 2592000,  # 30d (approx)
        }

        seconds = interval_map.get(interval)
        if not seconds:
            return None

        cutoff = self._to_ts() - seconds
        return self.get_price_at_or_after(ticker, cutoff)

    @staticmethod
    def _to_ts(ts: int | datetime | None = None) -> int:
        """Normalize input (None/int/datetime) to an integer unix timestamp (seconds)."""
        if ts is None:
            return int(datetime.now(timezone.utc).timestamp())
        if isinstance(ts, datetime):
            return int(ts.replace(tzinfo=timezone.utc).timestamp())
        return int(ts)
