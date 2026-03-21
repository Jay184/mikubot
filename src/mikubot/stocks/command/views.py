from io import BytesIO
from discord import Interaction, ButtonStyle, File, Embed, Color
from discord.ui import View, Button, button as view_button

from mikubot import Bot
from mikubot.stocks.intervals import SecurityIntervals
from mikubot.stocks.models import Portfolio, TransactionType

from .embeds import HelpEmbed, TransactionEmbed, PortfolioEmbed
from .modals import CancelModal, CreateOrderModal


class IntervalButton(Button["Interval"]):
    def __init__(self, interval: SecurityIntervals):
        super().__init__(
            style=ButtonStyle.secondary,
            label=interval.name.upper(),
        )
        self.interval = interval

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message(  # noqa
            "Loading...",
            ephemeral=True,
            delete_after=3,
        )

        self.view.value = self.interval
        self.view.stop()


class GraphIntervalView(View):
    def __init__(self, selected: SecurityIntervals | None = SecurityIntervals.day):
        super().__init__()
        self.value = selected

        for interval in SecurityIntervals:
            button = IntervalButton(interval)

            if interval == selected:
                button.style = ButtonStyle.primary
                button.disabled = True

            self.add_item(button)


class ConfirmView(View):
    def __init__(self):
        super().__init__()
        self.value = None

    @view_button(label="Confirm", style=ButtonStyle.green, emoji="✔️")
    async def confirm(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(  # noqa
            "Creating portfolio...",
            ephemeral=True,
            delete_after=3,
        )

        self.value = True
        self.stop()

    @view_button(label="Cancel", style=ButtonStyle.grey, emoji="❌")
    async def cancel(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(  # noqa
            "Cancelling.",
            ephemeral=True,
            delete_after=3,
        )

        self.value = False
        self.stop()


class PortfolioSelector(View):
    def __init__(self, bot: Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @view_button(label="Pending transactions", style=ButtonStyle.gray, emoji="📄")
    async def pending(self, interaction: Interaction, button: Button):
        portfolio = Portfolio.get(interaction.user.id)
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
                embeds=list(map(TransactionEmbed, pending[i:i+10])),
                ephemeral=True,
            )

    @view_button(label="Securities", style=ButtonStyle.gray, emoji="💱")
    async def prices(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)  # noqa

        securities = list(self.bot.market.securities.all().values())
        securities.sort(key=lambda s: s.config.key)

        embeds = []
        lines = []

        for sec in securities:
            price_old = self.bot.market.history.get_price_at_or_before_interval(sec.config.key, SecurityIntervals.day)
            price_old = price_old or sec.state.price
            price_now = sec.state.price
            change = (price_now - price_old) / price_old

            lines.append(
                f"- **{sec.config.key}** | _{sec.config.name}_ [ASK **{sec.ask:,.2f}** | BID **{sec.bid:,.2f}**] (**{change:+,.2%}**)")

        # Paginate if too many
        chunk_size = 30
        for i in range(0, len(lines), chunk_size):
            chunk = lines[i:i + chunk_size]

            embeds.append(Embed(
                title="Market Securities",
                description="\n".join(chunk),
                color=Color.blue()
            ))

        for i in range(0, len(embeds), 10):
            await interaction.followup.send(
                embeds=embeds[i:i + 10],
                ephemeral=True,
            )

        # Send graphs
        interval_view = GraphIntervalView()
        message = None

        while True:
            fig, _ = self.bot.market.graphs.create_price_matrix(securities, interval_view.value, cols=...)

            # Save figure to an in-memory file
            buffer = BytesIO()
            fig.savefig(buffer, format="png")
            buffer.seek(0)
            file = File(buffer, "stocks.png")

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

    @view_button(label="Cancel a transaction", style=ButtonStyle.red, emoji="✖️")
    async def cancel(self, interaction: Interaction, button: Button):
        if not self.bot.market.is_open:
            await interaction.response.send_message(  # noqa
                "The market is currently closed.",
                ephemeral=True,
                delete_after=3,
            )
            return

        modal = CancelModal(self.bot.market)
        await interaction.response.send_modal(modal)  # noqa

    @view_button(label="Sell", style=ButtonStyle.red, emoji="➖", row=1)
    async def sell(self, interaction: Interaction, button: Button):
        if not self.bot.market.is_open:
            await interaction.response.send_message(  # noqa
                "The market is currently closed.",
                ephemeral=True,
                delete_after=3,
            )
            return

        modal = CreateOrderModal(self.bot.market, TransactionType.SELL)
        await interaction.response.send_modal(modal)  # noqa

    @view_button(label="Buy", style=ButtonStyle.green, emoji="➕", row=1)
    async def buy(self, interaction: Interaction, button: Button):
        if not self.bot.market.is_open:
            await interaction.response.send_message(  # noqa
                "The market is currently closed.",
                ephemeral=True,
                delete_after=3,
            )
            return

        modal = CreateOrderModal(self.bot.market, TransactionType.BUY)
        await interaction.response.send_modal(modal)  # noqa

    @view_button(label="Refresh", style=ButtonStyle.gray, emoji="🔁", row=2)
    async def refresh(self, interaction: Interaction, button: Button):
        portfolio = Portfolio.get(interaction.user.id)
        embed = PortfolioEmbed(portfolio, interaction.user, self.bot.market, self.bot.settings.market)

        await interaction.response.send_message(  # noqa
            embed=embed,
            view=self,
            ephemeral=True,
        )

    @view_button(label="Info", style=ButtonStyle.gray, emoji="❔", row=2)
    async def help(self, interaction: Interaction, button: Button):
        settings = self.bot.settings.market

        await interaction.response.send_message(  # noqa
            embed=HelpEmbed(settings),
            ephemeral=True,
        )
