from discord import Interaction
from discord.utils import MISSING
from discord.ui import Modal, TextInput
from pydantic import TypeAdapter
from loguru import logger

from mikubot.stocks import Portfolio, Transaction, TransactionType
from mikubot.stocks.core import Market


class CancelModal(Modal, title="Select an order to cancel"):
    def __init__(
        self,
        market: Market,
        *,
        title: str = MISSING,
        timeout: float | None = None,
        custom_id: str = MISSING,
    ):
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)
        self.market = market

    transaction_id = TextInput(
        label="Transaction ID",
        placeholder="00000000-0000-0000-0000-000000000000",
        required=True,
    )

    async def on_submit(self, interaction: Interaction):
        check = self.market.can_cancel(self.transaction_id.value, interaction.user.id)

        if not check.allowed:
            raise ValueError(check.reason)

        self.market.tx_engine.cancel(self.transaction_id.value)

        success_message = "Order cancellation requested!"
        logger.info(f"Sent cancellation request for order {self.transaction_id.value}")
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
            delete_after=3,
        )

    async def on_error(self, interaction: Interaction, error: Exception):
        error_message = "Oops! Something went wrong."
        logger.exception(error)
        await interaction.response.send_message(  # noqa
            error_message,
            ephemeral=True,
            delete_after=3,
        )


class CreateOrderModal(Modal):
    def __init__(
        self,
        market: Market,
        order_type: TransactionType,
        *,
        title: str = MISSING,
        timeout: float | None = None,
        custom_id: str = MISSING,
    ):
        _title = title or order_type.value.title()
        super().__init__(title=_title, timeout=timeout, custom_id=custom_id)
        self.market = market
        self.order_type = order_type

        placeholder_index = 0 if order_type == TransactionType.BUY else 1
        limit_placeholders = self.limit_price.placeholder.split("|")
        self.limit_price.placeholder = limit_placeholders[placeholder_index]

        stop_placeholders = self.stop_price.placeholder.split("|")
        self.stop_price.placeholder = stop_placeholders[placeholder_index]

    security_key = TextInput(
        label="Ticker",
        placeholder="EDEN",
        required=True,
    )

    quantity = TextInput(
        label="Quantity",
        placeholder="1",
        default="1",
        required=True,
    )

    limit_price = TextInput(
        label="LIMIT",
        placeholder="(Optional) Maximum price to be paid.|(Optional) Minimum price to be reached.",
        required=False,
    )

    stop_price = TextInput(
        label="STOP",
        placeholder="(Optional) Minimum price to be paid.|(Optional) Maximum price to be reached.",
        required=False,
    )

    async def on_submit(self, interaction: Interaction):
        limit_price_value = self.limit_price.value.replace(",", "").strip()
        stop_price_value = self.stop_price.value.replace(",", "").strip()

        security = self.market.securities.get(self.security_key.value.upper())
        quantity = TypeAdapter(int).validate_strings(self.quantity.value)
        limit_price = TypeAdapter(float).validate_strings(limit_price_value) if len(limit_price_value) else None
        stop_price = TypeAdapter(float).validate_strings(stop_price_value) if len(stop_price_value) else None

        portfolio = Portfolio.get(interaction.user.id)

        if self.order_type == TransactionType.BUY:
            check = self.market.can_buy(security, portfolio, quantity, limit=limit_price, stop=stop_price)
        else:
            check = self.market.can_sell(security, portfolio, quantity, limit=limit_price, stop=stop_price)

        if not check.allowed:
            raise ValueError(check.reason)

        if self.order_type == TransactionType.BUY:
            transaction = self.market.tx_engine.buy(portfolio, security, quantity, limit=limit_price, stop=stop_price)
        else:
            transaction = self.market.tx_engine.sell(portfolio, security, quantity, limit=limit_price, stop=stop_price)

        success_message = "Order created!"
        logger.info(f"Created order {transaction.id} for {transaction.security_key}")
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
            delete_after=3,
        )

    async def on_error(self, interaction: Interaction, error: Exception):
        error_message = f"Oops! Something went wrong. {error}"
        logger.exception(error)
        await interaction.response.send_message(  # noqa
            error_message,
            ephemeral=True,
            delete_after=3,
        )
