from io import BytesIO
from datetime import datetime, timezone
from discord import Interaction, ButtonStyle, File, Embed
from discord.ui import View, Button, button as view_button

from mikubot import Bot
from mikubot.stocks.intervals import GraphInterval, IntervalData, DayIntervalData, WeekIntervalData, MonthIntervalData
from mikubot.stocks.models import Portfolio, Security, TransactionType

from .utils import create_security_embed, create_transaction_embed, create_portfolio_embed, next_occurrence
from .modals import CancelModal, CreateOrderModal


class IntervalButton(Button['Interval']):
    def __init__(self, interval: GraphInterval):
        super().__init__(
            style=ButtonStyle.secondary,
            label=interval.name.upper(),
        )
        self.interval = interval

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message(  # noqa
            'Loading...',
            ephemeral=True,
            delete_after=3,
        )

        self.view.value = self.interval
        self.view.stop()


class GraphIntervalView(View):
    def __init__(self, selected: GraphInterval | None = GraphInterval.day):
        super().__init__()
        self.value = selected

        for interval in GraphInterval:
            button = IntervalButton(interval)

            if interval == selected:
                button.style = ButtonStyle.primary
                button.disabled = True

            self.add_item(button)


class ConfirmView(View):
    def __init__(self):
        super().__init__()
        self.value = None

    @view_button(label='Confirm', style=ButtonStyle.green, emoji='✔️')
    async def confirm(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(  # noqa
            'Creating portfolio...',
            ephemeral=True,
            delete_after=3,
        )

        self.value = True
        self.stop()

    @view_button(label='Cancel', style=ButtonStyle.grey, emoji='❌')
    async def cancel(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(  # noqa
            'Cancelling.',
            ephemeral=True,
            delete_after=3,
        )

        self.value = False
        self.stop()


class PortfolioSelector(View):
    def __init__(self, bot: Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @view_button(label='Pending transactions', style=ButtonStyle.gray, emoji='📄')
    async def pending(self, interaction: Interaction, button: Button):
        portfolio = Portfolio.get(interaction.user.id)
        pending = [t for t in portfolio.get_transactions() if t.is_pending or t.is_cancellation_requested]

        if not pending:
            await interaction.response.send_message(  # noqa
                'No pending transactions',
                ephemeral=True,
                delete_after=3,
            )
            return

        await interaction.response.defer(ephemeral=True)  # noqa

        for i in range(0, len(pending), 10):
            await interaction.followup.send(
                embeds=list(map(create_transaction_embed, pending[i:i+10])),
                ephemeral=True,
            )

    @view_button(label='Securities', style=ButtonStyle.gray, emoji='💱')
    async def prices(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)  # noqa

        securities = [Security(key=k, **data) for k, data in self.bot.market.domain('securities').items()]
        securities.sort(key=lambda s: s.key)

        embeds = [create_security_embed(s) for s in securities]

        for i in range(0, len(securities), 10):
            await interaction.followup.send(
                embeds=embeds[i:i + 10],
                ephemeral=True,
            )

        # Send graphs
        interval_view = GraphIntervalView()
        message = None

        while True:
            intervals = {
                GraphInterval.day: DayIntervalData,
                GraphInterval.week: WeekIntervalData,
                GraphInterval.month: MonthIntervalData,
            }

            now = datetime.now(timezone.utc)
            interval = intervals[interval_view.value](now)

            data = [self.bot.market.get_price_graph_data(s.key, interval) for s in securities]
            fig, axes = self.bot.market.create_graph_matrix(*data, interval=interval)

            for ax, s, ax_data in zip(axes, securities, data):
                past = self.bot.market.get_price_history(s.key,
                   before=interval.start,
                   limit=1,
                )

                title = s.key
                past_price = ax_data[0][1] if len(ax_data) else None
                past_price = past[0][1] if len(past) else past_price

                if past_price:
                    percent = (s.price - past_price) / past_price
                    percent_sign = '-' if ((percent > 0) - (percent < 0)) < 0 else '+'
                    title += f' ({percent_sign}{100 * percent:,.2f}%)'

                ax.set_title(title)

            fig.tight_layout()

            # Save figure to an in-memory file
            buffer = BytesIO()
            fig.savefig(buffer, format="png")
            buffer.seek(0)
            file = File(buffer, 'stocks.png')

            if not message:
                message = await interaction.followup.send(
                    file=file,
                    ephemeral=True,
                    view=interval_view,
                    wait=True,
                )
            else:
                await message.edit(
                    attachments=[file],
                    view=interval_view,
                )

            if await interval_view.wait():
                break

            interval_view = GraphIntervalView(interval_view.value)

    @view_button(label='Cancel a transaction', style=ButtonStyle.red, emoji='✖️')
    async def cancel(self, interaction: Interaction, button: Button):
        if not self.bot.market.is_open:
            await interaction.response.send_message(  # noqa
                'The market is currently closed.',
                ephemeral=True,
                delete_after=3,
            )
            return

        modal = CancelModal(self.bot.market)
        await interaction.response.send_modal(modal)  # noqa

    @view_button(label='Sell', style=ButtonStyle.red, emoji='➖', row=1)
    async def sell(self, interaction: Interaction, button: Button):
        if not self.bot.market.is_open:
            await interaction.response.send_message(  # noqa
                'The market is currently closed.',
                ephemeral=True,
                delete_after=3,
            )
            return

        modal = CreateOrderModal(self.bot.market, TransactionType.SELL)
        await interaction.response.send_modal(modal)  # noqa

    @view_button(label='Buy', style=ButtonStyle.green, emoji='➕', row=1)
    async def buy(self, interaction: Interaction, button: Button):
        if not self.bot.market.is_open:
            await interaction.response.send_message(  # noqa
                'The market is currently closed.',
                ephemeral=True,
                delete_after=3,
            )
            return

        modal = CreateOrderModal(self.bot.market, TransactionType.BUY)
        await interaction.response.send_modal(modal)  # noqa

    @view_button(label='Refresh', style=ButtonStyle.gray, emoji='🔁', row=2)
    async def refresh(self, interaction: Interaction, button: Button):
        portfolio = Portfolio.get(interaction.user.id)
        embed = create_portfolio_embed(interaction.user, self.bot, portfolio)

        await interaction.response.send_message(  # noqa
            embed=embed,
            view=self,
            ephemeral=True,
        )

    @view_button(label='Info', style=ButtonStyle.gray, emoji='❔', row=2)
    async def help(self, interaction: Interaction, button: Button):
        settings = self.bot.settings.market

        next_open_timestamp = next_occurrence(settings.open_time).timestamp()
        next_close_timestamp = next_occurrence(settings.close_time).timestamp()

        help_text = f"""\
You can buy and sell fake stocks for fun in a small simulated economy. 🪙

Use the `Securities` button in your portfolio to see the available assets that can be traded.

- Interest rate: {settings.interest_rate * 100:,.2f}% per week (distributed mondays on market opening time).
- Order fee: {settings.order_fee:,.2f} per transaction in addition to {settings.order_fee_rate * 100:,.2f}% of the asset's market value.
- Starting credit: {settings.starting_credit:,.2f} when opening the portfolio.
- Market open time: <t:{int(next_open_timestamp)}:t>.
- Market close time: <t:{int(next_close_timestamp)}:t>.

✅ **Some beginner tips**

- You buy and sell using the 4 character ID of the security.
- You buy the ASK price and sell at the BID price.
- If your order isn't going through, check your LIMIT and STOP price.
- Interest rate only applies to cash that's NOT invested.
"""

        embed = Embed(
            title='💹 Eden stock market',
            description=help_text,
        )

        embed.set_footer(text='This is a work in progress.')

        await interaction.response.send_message(  # noqa
            embed=embed,
            ephemeral=True,
        )
