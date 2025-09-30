from datetime import datetime, timezone
from io import BytesIO
from typing import Literal

from discord import Interaction, User, File, Member
from discord import Embed, Color
from discord.ext import tasks
from discord.utils import MISSING
from discord.app_commands import Group, checks, describe, errors
from loguru import logger
from pydantic import ValidationError

from mikubot import Bot
from mikubot.stocks.models import Portfolio

from .utils import next_occurrence
from .embeds import HelpEmbed, PortfolioEmbed, SecurityEmbed, TransactionEmbed, TopPortfolioEmbed
from .views import ConfirmView, PortfolioSelector
from ..links import update_linked_prices
from ..intervals import SecurityIntervals


async def send_portfolio(interaction: Interaction, bot: Bot, user: User, interval: SecurityIntervals = SecurityIntervals.day):
    await interaction.response.defer(ephemeral=True)  # noqa

    if not bot.settings.market.enabled:
        await interaction.followup.send("Stock market is disabled.", ephemeral=True)  # noqa
        return

    portfolio = Portfolio.get(user.id)
    is_owner = interaction.user == user

    if not portfolio:
        if is_owner:
            confirm_view = ConfirmView()

            await interaction.followup.send(  # noqa
                "You don't have an open portfolio. Would you like to create one?",
                view=confirm_view,
                ephemeral=True,
            )

            await confirm_view.wait()
            message = await interaction.original_response()
            await message.delete()

            if not confirm_view.value:
                return

            portfolio = Portfolio(
                user_id=interaction.user.id,
                balance=bot.settings.market.starting_credit,
            )
            portfolio.save()
            bot.market.history.record_balance(portfolio)
            logger.info(f"Created a portfolio for {user.display_name} with {portfolio.balance}.")

        else:
            await interaction.followup.send(  # noqa
                f"{user.display_name} does not have an open portfolio.",
                ephemeral=True,
                allowed_mentions=None,
            )
            return

    show_securities = not bot.settings.market.hide_portfolio_securities or is_owner
    embed = PortfolioEmbed(portfolio, user, bot.market, bot.settings.market, include_securities=show_securities)
    portfolio_view = MISSING
    graph_file = MISSING

    if is_owner:
        portfolio_view = PortfolioSelector(bot)

        portfolio_view.cancel.disabled = not len([t for t in portfolio.get_transactions() if t.is_pending])
        portfolio_view.sell.disabled = not len(portfolio.positions)

        if not bot.market.is_open:
            portfolio_view.buy.disabled = True
            portfolio_view.sell.disabled = True
            portfolio_view.cancel.disabled = True

        fig, _ = bot.market.graphs.create_balance_graph(portfolio, interval)

        # Save figure to an in-memory file
        buffer = BytesIO()
        fig.savefig(buffer, format="png")
        buffer.seek(0)
        graph_file = File(buffer, "balance.png")

    await interaction.followup.send(  # noqa
        embed=embed,
        view=portfolio_view,
        file=graph_file,
        ephemeral=True,
        allowed_mentions=None,
    )


def register_tasks(bot: Bot) -> list[tasks.Loop]:
    @tasks.loop(time=bot.settings.market.open_time)
    async def on_market_open():
        logger.info("The market is now open.")
        current_timestamp = int(datetime.now(timezone.utc).timestamp())

        if datetime.now(timezone.utc).weekday() == 0:
            logger.info("Paying interest...")

            for k, data in bot.market.store.domain("portfolios").items():
                portfolio = Portfolio(user_id=k, **data)
                balance_before = portfolio.balance
                portfolio.balance *= 1 + bot.settings.market.interest_rate
                portfolio.save()
                bot.market.history.record_balance(portfolio, current_timestamp)
                logger.info(f"Portfolio #{k} gained +{portfolio.balance - balance_before:,.2f} interest.")

    @tasks.loop(time=bot.settings.market.close_time)
    async def on_market_close():
        logger.info("The market is now closed.")

    @tasks.loop(seconds=bot.settings.market.remote_update_interval)
    async def update_remote_link_prices():
        securities = bot.market.securities.all()
        update_linked_prices(bot.market, securities, bot.settings.market.remote_update_interval, local=False)

    @tasks.loop(seconds=bot.settings.market.local_update_interval)
    async def update_local_link_prices():
        securities = bot.market.securities.all()
        update_linked_prices(bot.market, securities, bot.settings.market.local_update_interval, local=True)

    return [
        on_market_open,
        on_market_close,
        update_remote_link_prices,
        update_local_link_prices,
    ]


def has_optional_role(item: int | None = None):
    def predicate(interaction: Interaction) -> bool:
        if isinstance(interaction.user, User):
            raise errors.NoPrivateMessage()

        if not item:
            return True

        role = interaction.user.get_role(item)

        if role is None:
            raise errors.MissingRole(item)
        return True

    return checks.check(predicate)


def is_market_admin(admins: list[int]):
    def predicate(interaction: Interaction) -> bool:
        return interaction.user.id in admins

    return checks.check(predicate)


def register_admin(bot: Bot) -> Group:
    admin_group = Group(
        name="admin",
        description="Admin commands",
    )

    @admin_group.command(
        name="setprice",
        description="Set the price of a security directly.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security you want to update. Example: TICK or FAKECOIN.",
        newprice="The new price to set for the asset.",
    )
    async def handler_admin_set_price(interaction: Interaction, ticker: str, newprice: float):
        sec = bot.market.securities.get(ticker)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        if newprice < 0:
            await interaction.response.send_message(  # noqa
                "❌ Price must be >= 0.",
                ephemeral=True,
            )
            return

        bot.market.set_price(ticker, newprice)

        await interaction.response.send_message(  # noqa
            f"✅ Set price of `{ticker}` to {newprice:+,.2f}", ephemeral=True
        )

    @admin_group.command(
        name="applychange",
        description="Apply a change to a security's price.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security to change.",
        change="The change to apply (e.g., -2.5% or -0.025).",
    )
    async def handler_admin_apply_change(interaction: Interaction, ticker: str, change: str):
        sec = bot.market.securities.get(ticker)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        if change.endswith("%"):
            pct = float(change.strip("%")) / 100
        else:
            pct = float(change)

        if pct < -1.0:
            await interaction.response.send_message(  # noqa
                "❌ Change must be >= -1.0 (-100%).",
                ephemeral=True,
            )
            return

        bot.market.apply_change(ticker, pct)

        await interaction.response.send_message(  # noqa
            f"✅ Applied change {pct:+,.2%} to `{ticker}` → new price {sec.state.price:+,.2f}",
            ephemeral=True,
        )

    @admin_group.command(
        name="view",
        description="View a user's portfolio.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        user="The Discord user whose portfolio you want to view.",
        interval="Interval used for the balance graph",
    )
    async def handler_admin_view(interaction: Interaction, user: Member, interval: SecurityIntervals = SecurityIntervals.day):
        portfolio = Portfolio.get(user.id)

        if not portfolio:
            await interaction.response.send_message(  # noqa
                f"No portfolio found for {user.display_name}.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)  # noqa

        embed = PortfolioEmbed(portfolio, user, bot.market, bot.settings.market, include_securities=True)
        fig, _ = bot.market.graphs.create_balance_graph(portfolio, interval)

        # Save figure to an in-memory file
        buffer = BytesIO()
        fig.savefig(buffer, format="png")
        buffer.seek(0)
        graph_file = File(buffer, "balance.png")

        await interaction.followup.send(  # noqa
            embed=embed,
            file=graph_file,
            ephemeral=True,
        )

    @admin_group.command(
        name="setpositions",
        description="Set the quantity of a security for a portfolio.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        user="The Discord user whose portfolio you want to edit.",
        ticker="The symbol of the security.",
        qty="The new quantity to set for all or a specific portfolio.",
    )
    async def handler_admin_set_positions(interaction: Interaction, user: Member, ticker: str, qty: float):
        portfolio = Portfolio.get(user.id)

        if not portfolio:
            await interaction.response.send_message(  # noqa
                f"Portfolio of {user.display_name} not found.",
                ephemeral=True,
            )
            return

        sec = bot.market.securities.get(ticker)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        bot.market.set_holdings(portfolio.user_id, ticker, qty)

        await interaction.response.send_message(  # noqa
            f"✅ Set position of `{ticker}` to {qty} for {user.display_name}",
            ephemeral=True,
        )

    @admin_group.command(
        name="addbalance",
        description="Set a user's portfolio balance.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        user="The Discord user whose balance you want to set.",
        amount="The amount of cash to add."
    )
    async def handler_admin_add_balance(interaction: Interaction, user: Member, amount: float):
        portfolio = Portfolio.get(user.id)

        if not portfolio:
            await interaction.response.send_message(  # noqa
                f"No portfolio found for {user.display_name}.",
                ephemeral=True,
            )
            return

        new_balance = bot.market.adjust_balance(portfolio.user_id, amount)

        await interaction.response.send_message(  # noqa
            f"✅ Set balance of {user.display_name} to {new_balance:+,.2f}",
            ephemeral=True,
        )

    @admin_group.command(
        name="sync",
        description="Manually sync a security's price or state.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        interval="Seconds since last sync.",
        ticker="The symbol of the security to sync.",
    )
    async def handler_admin_sync(interaction: Interaction, interval: float = 3600.0, ticker: str | None = None):
        if ticker:
            sec = bot.market.securities.get(ticker)
            if not sec:
                await interaction.response.send_message(  # noqa
                    f"Security `{ticker}` not found.",
                    ephemeral=True,
                )
                return

            securities = {ticker: sec}
        else:
            securities = bot.market.securities.all()

        changes = update_linked_prices(bot.market, securities, interval=interval, local=False)
        local_changes = update_linked_prices(bot.market, securities, interval=interval, local=True)

        for ticker, (local_change, local_price) in local_changes.items():
            if ticker in changes:
                remote_change, _ = changes[ticker]
                changes[ticker] = (remote_change + local_change, local_price)
            else:
                changes[ticker] = (local_change, local_price)

        if not changes:
            await interaction.response.send_message(  # noqa
                "No securities were updated.",
                ephemeral=True,
            )
            return

        embed = Embed(
            title="🔄 Sync Results",
            description="Securities updated during sync:\n" + "\n".join(f"Change: {change:+.2%}\nPrice: {price:,.2f}" for ticker, (change, price) in changes.items()),
            color=Color.green(),
        )

        await interaction.response.send_message(  # noqa
            embed=embed,
            ephemeral=True,
        )

    @admin_group.command(
        name="freeze",
        description="Freeze a security to prevent trading.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security to freeze."
    )
    async def handler_admin_freeze(interaction: Interaction, ticker: str):
        sec = bot.market.securities.get(ticker)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        bot.market.securities.freeze(ticker)

        await interaction.response.send_message(  # noqa
            f"✅ `{ticker}` has been frozen.",
            ephemeral=True,
        )

    @admin_group.command(
        name="unfree",
        description="Unfreeze a previously frozen security.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security to unfreeze."
    )
    async def handler_admin_unfreeze(interaction: Interaction, ticker: str):
        sec = bot.market.securities.get(ticker)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        bot.market.securities.unfreeze(ticker)

        await interaction.response.send_message(  # noqa
            f"✅ `{ticker}` has been unfrozen.",
            ephemeral=True,
        )

    @admin_group.command(
        name="delist",
        description="Delist a security.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security to delist.",
        mode="Refund mode for portfolios holding this security. Either `buy` or `refund`.",
    )
    async def handler_admin_delist(interaction: Interaction, ticker: str, mode: Literal["buy", "current"] = "buy"):
        sec = bot.market.securities.get(ticker)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        portfolios = [Portfolio(user_id=int(id_), **data) for id_, data in bot.market.store.domain("portfolios").items()]

        for portfolio in portfolios:
            if ticker in portfolio.positions:
                bot.market.refund_position(portfolio.user_id, ticker, refund_mode=mode)

        bot.market.securities.delist(ticker)
        bot.market.securities.freeze(ticker)

        await interaction.response.send_message(  # noqa
            f"✅ `{ticker}` has been delisted and frozen. Holders compensated by `{mode}`.",
            ephemeral=True
        )

    @admin_group.command(
        name="list",
        description="List a security again.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security to list.",
    )
    async def handler_admin_list(interaction: Interaction, ticker: str):
        sec = bot.market.securities.get(ticker, include_delisted=True)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        bot.market.securities.list(ticker)
        bot.market.securities.unfreeze(ticker)

        await interaction.response.send_message(  # noqa
            f"✅ `{ticker}` has been listed and unfrozen.",
            ephemeral=True
        )

    @admin_group.command(
        name="wipehistory",
        description="Wipes all price history of a security. The security itself is not deleted.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security whose history you want to wipe.",
    )
    async def handler_admin_wipehistory(interaction: Interaction, ticker: str):
        sec = bot.market.securities.get(ticker)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        bot.market.store.execute("DELETE FROM price_history WHERE security_key = ?", (ticker,))
        bot.market.history.record_price(ticker, sec.state.price)

        await interaction.response.send_message(  # noqa
            f"✅ Wiped all price history for `{ticker}`.",
            ephemeral=True
        )

    @admin_group.command(
        name="wipe",
        description="Reset a security's runtime state. Historical prices and transactions are preserved."
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security whose state you want to wipe."
    )
    async def handler_admin_wipe(interaction: Interaction, ticker: str):
        sec = bot.market.securities.get(ticker, include_delisted=True)

        if not sec:
            await interaction.response.send_message(  # noqa
                f"Security `{ticker}` not found.",
                ephemeral=True,
            )
            return

        bot.market.store.remove("securities", ticker)
        sec = bot.market.securities.get(ticker)  # Creates a new state
        sec.save_state()
        bot.market.history.record_price(ticker, sec.state.price)

        await interaction.response.send_message(  # noqa
            f"✅ Security `{ticker}` state has been wiped and reset to config defaults.",
            ephemeral=True,
        )

    @admin_group.command(
        name="swap",
        description="Swap holdings from one security to another at a given ratio.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @is_market_admin(bot.settings.market.admins)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        oldticker="The symbol of the security to replace.",
        newticker="The symbol of the security to assign to holders.",
        ratio="The conversion ratio applied to old holdings.",
        user="User to swap asset for. Leave empty to execute globally.",
    )
    async def handler_admin_swap(interaction: Interaction, oldticker: str, newticker: str, ratio: float = 1.0, user: Member | None = None):
        old_sec = bot.market.securities.get(oldticker)
        new_sec = bot.market.securities.get(newticker)

        if not old_sec or not new_sec:
            await interaction.response.send_message(  # noqa
                "One or both tickers not found.",
                ephemeral=True,
            )
            return

        if user:
            portfolio = Portfolio.get(user.id)

            if not portfolio:
                await interaction.response.send_message(  # noqa
                    f"Portfolio of {user.display_name} not found.",
                    ephemeral=True,
                )
                return

            portfolios = [portfolio]
        else:
            portfolio_data = bot.market.store.domain("portfolios").items()
            portfolios = [Portfolio(user_id=k, **data) for k, data in portfolio_data]

        count = 0
        for portfolio in portfolios:
            position = portfolio.positions.get(oldticker)
            qty = position.quantity if position else 0

            if qty > 0:
                new_qty = qty * ratio

                bot.market.set_holdings(user.id, oldticker, 0, record=False)
                bot.market.set_holdings(user.id, newticker, new_qty)
                count += 1

        await interaction.response.send_message(  # noqa
            f"✅ Swapped `{oldticker}` → `{newticker}` at ratio {ratio:,.2f}. Updated {count} portfolios.",
            ephemeral=True,
        )

    @handler_admin_set_price.error
    @handler_admin_apply_change.error
    @handler_admin_view.error
    @handler_admin_set_positions.error
    @handler_admin_add_balance.error
    @handler_admin_sync.error
    @handler_admin_freeze.error
    @handler_admin_unfreeze.error
    @handler_admin_delist.error
    @handler_admin_wipehistory.error
    @handler_admin_wipe.error
    @handler_admin_swap.error
    async def error_handler(interaction: Interaction, error: errors.CommandInvokeError):
        if isinstance(error, errors.CheckFailure):
            await interaction.response.send_message(  # noqa
                "You're missing privileges to run this command.",
                ephemeral=True,
            )
            return

        logger.exception(error)
        await interaction.response.send_message(  # noqa
            str(error.original),
            ephemeral=True,
        )

    return admin_group


def register(bot: Bot):
    _tasks = register_tasks(bot)

    for task in _tasks:
        task.start()

    command_group = Group(
        name="portfolio",
        description="Manage your Eden stock portfolio.",
    )

    @command_group.command(
        name="view",
        description="View your or somebody else's portfolio.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        user="User you'd like to see the portfolio off. Leave empty to view your own",
        interval="Interval used for the balance graph",
    )
    async def handler_view(interaction: Interaction, user: User | None = None, interval: SecurityIntervals = SecurityIntervals.day):
        await send_portfolio(interaction, bot, user or interaction.user, interval)

    @command_group.command(
        name="assets",
        description="Show a list of all assets you can trade.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        interval="Interval used for the balance graph",
        ticker="The symbol of the security you want to buy. For example, TICK or FAKECOIN. Make sure the ticker exists in the market.",
    )
    async def handler_assets(interaction: Interaction, interval: SecurityIntervals = SecurityIntervals.day, ticker: str | None = None):
        if ticker:
            security = bot.market.securities.get(ticker)

            if not security:
                await interaction.response.send_message(  # noqa
                    "This asset doesn't exist.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)  # noqa
            security_embeds = [SecurityEmbed(security, bot.market, interval)]
            fig, _ = bot.market.graphs.create_price_matrix([security], interval, cols=1, fig_width=16, fig_height=9)
        else:
            await interaction.response.defer(ephemeral=True)  # noqa
            securities = list(bot.market.securities.all().values())
            securities.sort(key=lambda s: s.config.key)

            security_embeds = []
            lines = []

            for sec in securities:
                price_old = bot.market.history.get_price_at_or_before_interval(sec.config.key, interval)
                price_old = price_old or sec.state.price
                price_now = sec.state.price
                change = (price_now - price_old) / price_old

                lines.append(f"- **{sec.config.key}** | _{sec.config.name}_ [ASK **{sec.ask:,.2f}** | BID **{sec.bid:,.2f}**] (**{change:+,.2%}**)")

            # Paginate if too many
            chunk_size = 30
            for i in range(0, len(lines), chunk_size):
                chunk = lines[i:i + chunk_size]

                security_embeds.append(Embed(
                    title="Market Securities",
                    description="\n".join(chunk),
                    color=Color.blue()
                ))

            fig, _ = bot.market.graphs.create_price_matrix(securities, interval, cols=...)

        # Save figure to an in-memory file
        buffer = BytesIO()
        fig.savefig(buffer, format="png")
        buffer.seek(0)
        file = File(buffer, "stocks.png")

        for i in range(0, len(security_embeds), 10):
            await interaction.followup.send(
                embeds=security_embeds[i:i + 10],
                ephemeral=True,
            )

        await interaction.followup.send(  # noqa
            file=file,
            ephemeral=True,
        )

    @command_group.command(
        name="transactions",
        description="Show all pending transactions.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    async def handler_transactions(interaction: Interaction):
        portfolio = Portfolio.get(interaction.user.id)

        if not portfolio:
            await interaction.followup.send(  # noqa
                "You don't have an open portfolio.",
                ephemeral=True,
            )

        pending = [t for t in portfolio.get_transactions() if t.is_pending or t.is_cancellation_requested]

        if not pending:
            await interaction.response.send_message(  # noqa
                "No pending transactions",
                ephemeral=True,
                delete_after=3,
            )
            return

        await interaction.response.defer(ephemeral=True)  # noqa

        for i in range(0, len(pending), 10):
            await interaction.followup.send(
                embeds=list(map(TransactionEmbed, pending[i:i + 10])),
                ephemeral=True,
            )

    @command_group.command(
        name="top",
        description="Shows the top richest users.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    async def handler_top(interaction: Interaction):
        def lookup_name(user_id: int) -> str:
            user = bot.get_user(user_id)
            return user.display_name if user else f"User ID {user_id}"

        top_portfolios = bot.market.get_top_portfolios()
        top_portfolios = [(lookup_name(p.user_id), p) for p in top_portfolios]

        await interaction.response.send_message(  # noqa
            embed=TopPortfolioEmbed(top_portfolios),
            ephemeral=True,
            allowed_mentions=None,
        )

    @command_group.command(
        name="buy",
        description="Creates a buy order for a security.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security you want to buy. For example, TICK or FAKECOIN. Make sure the ticker exists in the market.",
        quantity="How many units of the security you want to purchase. Must be a positive integer. Default: 1",
        limit="A maximum price you are willing to pay per unit.",
        stop="A trigger price for a stop order: the purchase will only occur if the security reaches this price.",
    )
    async def handler_buy(interaction: Interaction, ticker: str, quantity: int = 1, limit: float | None = None, stop: float | None = None):
        portfolio = Portfolio.get(interaction.user.id)
        security = bot.market.securities.get(ticker)

        try:
           transaction = bot.market.tx_engine.buy(portfolio, security, quantity, limit=limit, stop=stop)
        except ValidationError:
            raise ValueError("Invalid order.")

        success_message = "Order created!"
        logger.info(f"Created order {transaction.id} for {transaction.security_key}")
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
        )

    @command_group.command(
        name="sell",
        description="Creates a sell order for a security you own.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    @describe(
        ticker="The symbol of the security you want to buy. For example, TICK or FAKECOIN. Make sure the ticker exists in the market.",
        quantity="The number of units of the security you want to sell. Must be a positive integer. Default: 1",
        limit="The minimum price per unit you are willing to accept.",
        stop="A stop price to automatically trigger a market sell if the security’s price drops to or below this value. Useful for limiting losses.",
    )
    async def handler_sell(interaction: Interaction, ticker: str, quantity: int = 1, limit: float | None = None, stop: float | None = None):
        portfolio = Portfolio.get(interaction.user.id)
        security = bot.market.securities.get(ticker)

        try:
           transaction = bot.market.tx_engine.sell(portfolio, security, quantity, limit=limit, stop=stop)
        except ValidationError:
            raise ValueError("Invalid order.")

        success_message = "Order created!"
        logger.info(f"Created order {transaction.id} for {transaction.security_key}")
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
        )

    @command_group.command(
        name="cancel",
        description="Cancel a previously created order.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    @describe(order_id="The ID of the order you wish to cancel.")
    async def handler_cancel(interaction: Interaction, order_id: str):
        try:
            bot.market.tx_engine.cancel(order_id, portfolio_id=interaction.user.id)
        except ValidationError:
            raise ValueError("Invalid order.")

        success_message = "Order cancellation requested!"
        logger.info(f"Sent cancellation request for order {order_id}")
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
        )

    @command_group.command(
        name="help",
        description="Get help about the Eden stock market.",
    )
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    async def handler_help(interaction: Interaction):
        await interaction.response.send_message(  # noqa
            embed=HelpEmbed(bot.settings.market),
            ephemeral=True,
            allowed_mentions=None,
        )

    admin_group = register_admin(bot)
    command_group.add_command(admin_group)
    bot.tree.add_command(command_group)

    @bot.tree.context_menu(name="View Eden portfolio")
    @checks.bot_has_permissions(send_messages=True)
    @has_optional_role(bot.settings.market.required_role)
    async def context_handler(interaction: Interaction, user: User):
        await send_portfolio(interaction, bot, user)

    @handler_view.error
    @handler_help.error
    @handler_assets.error
    @handler_transactions.error
    @handler_top.error
    @handler_buy.error
    @handler_sell.error
    @handler_cancel.error
    async def error_handler(interaction: Interaction, error: errors.CommandInvokeError):
        logger.exception(error)
        await interaction.response.send_message(  # noqa
            str(error.original),
            ephemeral=True,
        )
