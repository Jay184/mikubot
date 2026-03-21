from discord import Embed, User, Member, Color
from datetime import datetime, timezone

from mikubot.config import StockMarketSettings
from ..core import Market
from ..intervals import SecurityIntervals
from ..models import Security, Transaction, Portfolio, Position
from .utils import next_occurrence


class HelpEmbed(Embed):
    def __init__(self, settings: StockMarketSettings):
        next_open_timestamp = next_occurrence(settings.open_time).timestamp()
        next_close_timestamp = next_occurrence(settings.close_time).timestamp()

        help_text = f"""\
        📊 Welcome to the Fake Stock Market! 🪙
        Trade made-up securities in a small simulated economy.  
        *(Don’t worry — no real money is involved!)*

        ⚙️ **Market Rules**
        - **Interest rate**: {settings.interest_rate:,.2%}% per week  
          (paid on Mondays when the market opens, but only on uninvested cash).
        - **Order fee**: {settings.order_fee:,.2f} + {settings.order_fee_rate:,.2%}% of the trade value.
        - **Starting credit**: {settings.starting_credit:,.2f} when you open a portfolio.
        - **Market hours**:  
          - Opens: <t:{int(next_open_timestamp)}:t>  
          - Closes: <t:{int(next_close_timestamp)}:t>

        ✅ **Beginner Tips**
        - Trade using the **4-letter ticker** (e.g. `ABCD`).
        - You **buy** at the higher **ASK** price, and **sell** at the lower **BID** price.  
          → Even if your asset is “up,” you might sell for less than your buy-in.
        - If your order isn’t going through, check your **LIMIT** and **STOP** prices.
        - Keep in mind: interest only applies to **cash sitting idle**, not invested money.
        """

        super().__init__(
            title="💹 Eden stock market",
            description=help_text,
        )

        self.set_footer(text="This is a work in progress.")


class SecurityEmbed(Embed):
    def __init__(self, security: Security, market: Market, interval: SecurityIntervals = SecurityIntervals.day):
        price_old = market.history.get_price_at_or_before_interval(security.config.key, interval)
        price_old = price_old or security.state.price
        price_now = security.state.price
        change = (price_now - price_old) / price_old

        super().__init__(
            title=security.config.key,
            description=f"{security.state.price:,.2f} ({change:+,.2%})"
        )

        self.set_author(
            name=security.config.name,
            icon_url=security.config.icon_url,
        )

        self.add_field(name="ASK", value=f"{security.ask:,.2f}")
        self.add_field(name="BID", value=f"{security.bid:,.2f}")


class TransactionEmbed(Embed):
    def __init__(self, trans: Transaction):
        super().__init__(
            type="article",
            title=f"📄 `{trans.id}`",
            color=0x663311,
            description=f"{trans.type.value.title()} **{trans.security_key}**",
            timestamp=trans.creation_time,
        )

        self.set_footer(text=f"Status: {trans.status.value.lower()}")

        self.add_field(
            name="Quantity",
            value=trans.quantity,
            inline=False,
        )

        if trans.limit is not None:
            self.add_field(
                name="Limit price",
                value=f"{trans.limit:,.2f}",
            )

        if trans.stop is not None:
            self.add_field(
                name="Stop price",
                value=f"{trans.stop:,.2f}",
            )

        self.add_field(
            name="Expiry",
            value=f"<t:{int(trans.expiration_time.timestamp())}:f>"
        )

        if trans.cancellation_time is not None:
            self.add_field(
                name="Cancellation requested",
                value=f"<t:{int(trans.cancellation_time.timestamp())}:f>",
                inline=False,
            )

        if trans.is_executed:
            self.add_field(
                name="Execution time",
                value=f"<t:{int(trans.execution_time.timestamp())}:f>",
                inline=False,
            )

            self.add_field(
                name="Execution price",
                value=f"{trans.price:,.2f}",
                inline=False,
            )

            if trans.order_fee > 0:
                self.add_field(
                    name="Order fee",
                    value=f"{trans.order_fee:,.2f}",
                    inline=False,
                )

        elif trans.is_cancelled:
            self.add_field(
                name="Cancelled",
                value=f"<t:{int(trans.cancelled_time.timestamp())}:f>",
                inline=False,
            )


class PortfolioEmbed(Embed):
    def __init__(self, portfolio: Portfolio, user: User | Member, market: Market, settings: StockMarketSettings, *, interval: SecurityIntervals = SecurityIntervals.day, include_securities: bool = True):
        now = datetime.now(timezone.utc)

        def format_quantity(qty: float) -> str:
            if qty.is_integer():
                return f"{int(qty)}"
            elif (qty * 10).is_integer():
                return f"{qty:,.1f}"
            else:
                return f"{qty:,.2f}"

        def format_message(p: Position, s: Security) -> str:
            pnl = p.unrealized_pnl(s.state)
            change = p.unrealized_pnl_change(s.state)
            qty_str = format_quantity(p.quantity)
            return f" - **{s.config.key}** ({qty_str}x): {s.state.price:,.2f} ({pnl:+,.2f}, {change:+,.2%} since buy)"

        securities_held = {k: (p, market.securities.get(k)) for k, p in portfolio.positions.items()}
        portfolio_text = None

        if include_securities:
            portfolio_text = "\n".join(format_message(p, s) for p, s in securities_held.values())

        super().__init__(
            title="💹 Portfolio",
            description=portfolio_text,
            color=0x00a700,
            timestamp=now,
        )

        self.set_author(
            name=user.display_name,
            icon_url=user.avatar.url,
        )

        self.set_footer(
            text="This is a work in progress.",
        )

        self.add_field(
            name="💸 Balance",
            value=f"{portfolio.total_balance:,.2f}",
            inline=True,
        )

        self.add_field(
            name="🪙 Buying power",
            value=f"{portfolio.balance:,.2f}",
            inline=True,
        )

        if not market.is_open:
            next_open_timestamp = next_occurrence(settings.open_time).timestamp()
            self.description = f"💤 Market is closed right now (opens at <t:{int(next_open_timestamp)}:t>).\n\n{self.description}"


class TopPortfolioEmbed(Embed):
    def __init__(self, portfolios: list[tuple[str, Portfolio]]):
        super().__init__(
            title="💰 Eden Stock Market Leaderboard",
            description="The richest traders in the server!",
            color=Color.gold()
        )

        for rank, (username, portfolio) in enumerate(portfolios, start=1):
            self.add_field(
                name=f"{rank}. {username}",
                value=f"💵 Cash: ${portfolio.balance:,.2f}\n📈 Total: ${portfolio.total_balance:,.2f}",
                inline=False
            )