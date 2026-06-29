from loguru import logger
from datetime import datetime, timezone, timedelta
import yfinance as yf
import random

from .core import Market
from .derivative_rules.base import KnockoutException
from .models import Security, SecurityLinkConfig


def update_linked_prices(market: Market, securities: dict[str, Security], interval: float, *, local: bool = False) -> dict[str, tuple[float, float]]:
    now = datetime.now(timezone.utc)
    changes = {}
    cache = {}

    for ticker, sec in securities.items():
        link = sec.config.link
        check = market.can_sync(sec, now=now, interval=interval, local=local)

        if not check.allowed:
            continue

        # Select the right change function
        if local:
            change = get_local_change(link, market, now, int(interval))
            tag = "LOCAL"
        else:
            change = get_remote_change(link, int(interval), cache)
            tag = "REMOTE"

        try:
            for rule in link.derivative_rules:
                rule_instance = rule.create(market, sec)
                change = rule_instance.apply(sec, change, interval)
        except KnockoutException as e:
            logger.info(f"[KO] {e}")
            change = -1.0

        new_price = max(0.0, sec.state.price * (1.0 + change))
        if abs(change) < 1e-12 or abs(sec.state.price - new_price) < 1e-12:
            continue  # skip updates if no effective change

        sec.state.price = new_price
        sec.state.link.last_synced = now
        sec.save_state()

        changes[ticker] = (change, new_price)

        market.history.record_price(sec.config.key, sec.state.price, int(now.timestamp()))
        for portfolio in sec.get_holders():
            market.history.record_balance(portfolio, int(now.timestamp()))

        logger.info(f"[{tag}] {sec.config.key}: {change:+,.2%} applied")

    return changes


def get_remote_change(link_config: SecurityLinkConfig, seconds: int, cache: dict[str, float] = None) -> float:
    if not link_config.remotes:
        return 0.0

    cache = cache or {}

    def _handle_ticker(t: str) -> float:
        change = cache.get(t) or get_change_for_interval(t, seconds)
        cache[t] = change
        return change

    changes = [_handle_ticker(t) for t in link_config.remotes]
    return _aggregate_changes(changes, link_config.multiplier, link_config.noise)


def get_local_change(link_config: SecurityLinkConfig, market: Market, now: datetime, seconds: int) -> float:
    if not link_config.tickers:
        return 0.0

    now_ts = int(now.timestamp())
    cutoff_ts = now_ts - seconds
    changes = []

    for ticker in link_config.tickers:
        # Get price at or before cutoff
        price_old = market.history.get_price_at_or_before(ticker, cutoff_ts)
        price_new = market.history.get_price_at_or_before(ticker, now_ts)

        if price_old and price_new:
            if price_old > 0:
                changes.append((price_new - price_old) / price_old)

    return _aggregate_changes(changes, link_config.multiplier, link_config.noise)


def get_change_for_interval(ticker: str, seconds: int) -> float:
    try:
        stock = yf.Ticker(ticker)

        # Pick granularity based on interval
        if seconds < 3600:
            # Use 5-minute candles
            hist = stock.history(period="1d", interval="5m", timeout=3)
            steps = max(1, seconds // 300)  # 300s = 5m
        else:
            # Use hourly candles
            hist = stock.history(period="5d", interval="1h", timeout=3)
            steps = max(1, seconds // 3600)  # 3600s = 1h

        if hist.empty:
            raise RuntimeError(f"Empty history")

        if len(hist) <= steps:
            return 0.0

        old, new = hist["Close"].iloc[-(steps + 1)], hist["Close"].iloc[-1]
        return (new - old) / old if old else 0.0

    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return 0.0


def _aggregate_changes(changes: list[float], multiplier: float, noise: float) -> float:
    if not changes:
        return 0.0

    change = sum(changes) / len(changes)
    change *= multiplier

    if noise > 0.0:
        change += random.uniform(-noise, noise)

    return change
