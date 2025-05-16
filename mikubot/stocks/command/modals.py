from discord import Interaction
from discord.utils import MISSING
from discord.ui import Modal, TextInput
from pydantic import TypeAdapter
from loguru import logger

from mikubot.stocks import Portfolio, Security, Transaction, TransactionType
from mikubot.stocks.market import Market


class CancelModal(Modal, title='Select an order to cancel'):
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
        label='Transaction ID',
        placeholder='00000000-0000-0000-0000-000000000000',
        required=True,
    )

    async def on_submit(self, interaction: Interaction):
        if not self.market.is_open:
            raise ValueError('Market is closed.')

        transaction = Transaction.get(self.transaction_id.value)

        if transaction.user_id != interaction.user.id:
            raise ValueError('Unable to cancel order.')

        self.market.cancel(str(transaction.id))

        success_message = 'Order cancellation requested!'
        logger.info(f'Sent cancellation request for order {transaction.id}')
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
            delete_after=3,
        )

    async def on_error(self, interaction: Interaction, error: Exception):
        error_message = 'Oops! Something went wrong.'
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
        limit_placeholders = self.limit_price.placeholder.split('|')
        self.limit_price.placeholder = limit_placeholders[placeholder_index]

        stop_placeholders = self.stop_price.placeholder.split('|')
        self.stop_price.placeholder = stop_placeholders[placeholder_index]

    security_key = TextInput(
        label='Security ID',
        placeholder='EDEN',
        required=True,
    )

    quantity = TextInput(
        label='Quantity',
        placeholder='1',
        default='1',
        required=True,
    )

    limit_price = TextInput(
        label='LIMIT',
        placeholder='(Optional) Maximum price to be paid.|(Optional) Minimum price to be reached.',
        required=False,
    )

    stop_price = TextInput(
        label='STOP',
        placeholder='(Optional) Minimum price to be paid.|(Optional) Maximum price to be reached.',
        required=False,
    )

    async def on_submit(self, interaction: Interaction):
        if not self.market.is_open:
            raise ValueError('Market is closed right now.')

        limit_price_value = self.limit_price.value.replace(',', '').strip()
        stop_price_value = self.stop_price.value.replace(',', '').strip()

        security = Security.get(self.security_key.value.upper())
        quantity = TypeAdapter(int).validate_strings(self.quantity.value)
        limit_price = TypeAdapter(float).validate_strings(limit_price_value) if len(limit_price_value) else None
        stop_price = TypeAdapter(float).validate_strings(stop_price_value) if len(stop_price_value) else None

        if not security:
            raise ValueError('There is no such security to trade with.')

        if quantity <= 0:
            raise ValueError('Please provide positive quantities.')

        portfolio = Portfolio.get(interaction.user.id)

        if self.order_type == TransactionType.BUY:
            transaction = self.market.buy(portfolio, security, quantity, limit=limit_price, stop=stop_price)
        else:
            transaction = self.market.sell(portfolio, security, quantity, limit=limit_price, stop=stop_price)

        success_message = 'Order created!'
        logger.info(f"Created order {transaction.id} for {transaction.security_key}")
        await interaction.response.send_message(  # noqa
            success_message,
            ephemeral=True,
            delete_after=3,
        )

    async def on_error(self, interaction: Interaction, error: Exception):
        error_message = f'Oops! Something went wrong. {error}'
        logger.exception(error)
        await interaction.response.send_message(  # noqa
            error_message,
            ephemeral=True,
            delete_after=3,
        )
