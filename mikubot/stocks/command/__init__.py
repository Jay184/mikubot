from datetime import datetime, timezone
from io import BytesIO
from discord import Interaction, User, File
from discord.ext import tasks
from discord.utils import MISSING
from discord.app_commands import checks, describe
from loguru import logger

from mikubot import Bot
from mikubot.stocks.models import Portfolio

from .utils import create_security_embed, create_transaction_embed, create_portfolio_embed, next_occurrence
from .views import ConfirmView, PortfolioSelector
from ..intervals import GraphInterval, DayIntervalData, WeekIntervalData, MonthIntervalData


async def send_portfolio(interaction: Interaction, bot: Bot, user: User):
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
                'You don\'t have an open portfolio. Would you like to create one?',
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
            bot.market.record_balance(portfolio)
            logger.info(f'Created a portfolio for {user.display_name} with {portfolio.balance}.')

        else:
            await interaction.followup.send(  # noqa
                f'{user.display_name} does not have an open portfolio.',
                ephemeral=True,
                allowed_mentions=None,
            )
            return

    show_securities = not bot.settings.market.hide_portfolio_securities or is_owner
    embed = create_portfolio_embed(user, bot, portfolio, include_securities=show_securities)
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

        # TODO sophisticate this a little
        intervals = {
            GraphInterval.day: DayIntervalData,
            GraphInterval.week: WeekIntervalData,
            GraphInterval.month: MonthIntervalData,
        }

        now = datetime.now(timezone.utc)
        # interval = intervals[interval_view.value](now)
        interval = intervals[GraphInterval.month](now)

        data = bot.market.get_balance_graph_data(portfolio.user_id, interval)
        fig, ax = bot.market.create_graph(data, interval=interval)
        ax.set_ylabel("Balance")
        fig.tight_layout()

        # Save figure to an in-memory file
        buffer = BytesIO()
        fig.savefig(buffer, format="png")
        buffer.seek(0)
        graph_file = File(buffer, 'balance.png')

    await interaction.followup.send(  # noqa
        embed=embed,
        view=portfolio_view,
        file=graph_file,
        ephemeral=True,
        allowed_mentions=None,
    )


def register(bot: Bot):
    @tasks.loop(time=bot.settings.market.open_time)
    async def on_market_open():
        logger.info('The market is now open.')

        if datetime.now(timezone.utc).weekday() == 0:
            logger.info('Paying interest...')

            for k, data in bot.market.domain('portfolios').items():
                portfolio = Portfolio(user_id=k, **data)
                balance_before = portfolio.balance
                portfolio.balance *= 1 + bot.settings.market.interest_rate
                logger.info(f'Portfolio #{k} gained +{portfolio.balance - balance_before:,.2f} interest.')
                portfolio.save()

    @tasks.loop(time=bot.settings.market.close_time)
    async def on_market_close():
        logger.info('The market is now closed.')

    on_market_open.start()
    on_market_close.start()

    @bot.tree.command(name="portfolio", description="Manage your Eden stock portfolio.")
    @checks.bot_has_permissions(send_messages=True)
    @checks.has_role(bot.settings.market.required_role)
    @describe(user="User you want to check the portfolio off.")
    async def handler(interaction: Interaction, user: User | None = None):
        await send_portfolio(interaction, bot, user or interaction.user)

    @bot.tree.context_menu(name='View Eden portfolio')
    @checks.bot_has_permissions(send_messages=True)
    @checks.has_role(bot.settings.market.required_role)
    async def context_handler(interaction: Interaction, user: User):
        await send_portfolio(interaction, bot, user)

    @handler.error
    async def error_handler(interaction: Interaction, error):
        logger.exception(error)
        await interaction.response.send_message(  # noqa
            str(error),
            ephemeral=True,
        )
