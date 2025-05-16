from datetime import datetime, time, timedelta, timezone
from discord import Embed, User
from mikubot import Bot
from ..models import Portfolio, Security, Transaction, Position


def next_occurrence(target_time: time) -> datetime:
    now = datetime.now(timezone.utc)
    next_dt = now.replace(hour=target_time.hour, minute=target_time.minute,
                          second=target_time.second, microsecond=target_time.microsecond)
    if now >= next_dt:
        next_dt += timedelta(days=1)

    return next_dt


def create_portfolio_embed(user: User, bot: Bot, portfolio: Portfolio, *, include_securities: bool = True) -> Embed:
    def sign(x: float) -> int:
        return (x > 0) - (x < 0)

    def format_message(p: Position, s: Security) -> str:
        unrealised_return = p.unrealized_pnl(s)

        signs = {
            -1: '-',
            0: '',
            1: '+',
        }

        return_sign = signs[sign(unrealised_return)]

        return f' - **{s.key}** ({p.quantity}x): {s.price:,.2f} ({return_sign}{unrealised_return:,.2f} since buy)'

    securities_held = {k: (p, Security.get(k)) for k, p in portfolio.positions.items()}
    portfolio_text = None

    if include_securities:
        portfolio_text = '\n'.join(format_message(p, s) for p, s in securities_held.values())

    embed = Embed(
        title='💹 Portfolio',
        description=portfolio_text,
        color=0x00a700,
        timestamp=datetime.now(timezone.utc),
    )

    embed.set_author(
        name=user.display_name,
        icon_url=user.avatar.url,
    )

    embed.set_footer(
        text='This is a work in progress.',
    )

    embed.add_field(
        name='💸 Balance',
        value=f'{portfolio.total_balance:,.2f}',
        inline=True,
    )

    embed.add_field(
        name='🪙 Buying power',
        value=f'{portfolio.balance:,.2f}',
        inline=True,
    )

    if not bot.market.is_open:
        next_open_timestamp = next_occurrence(bot.settings.market.open_time).timestamp()
        embed.description = f'💤 Market is closed right now (opens at <t:{int(next_open_timestamp)}:t>).\n\n{embed.description}'

    return embed


def create_transaction_embed(trans: Transaction) -> Embed:
    embed = Embed(
        type='article',
        title=f'📄 `{trans.id}`',
        color=0x663311,
        description=f'{trans.type.value.title()} **{trans.security_key}**',
        timestamp=trans.creation_time,
    )

    embed.set_footer(text=f'Status: {trans.status.value.lower()}')

    embed.add_field(
        name='Quantity',
        value=trans.quantity,
        inline=False,
    )

    if trans.limit is not None:
        embed.add_field(
            name='Limit price',
            value=f'{trans.limit:,.2f}',
        )

    if trans.stop is not None:
        embed.add_field(
            name='Stop price',
            value=f'{trans.stop:,.2f}',
        )

    embed.add_field(
        name='Expiry',
        value=f'<t:{int(trans.expiration_time.timestamp())}:f>'
    )

    if trans.cancellation_time is not None:
        embed.add_field(
            name='Cancellation requested',
            value=f'<t:{int(trans.cancellation_time.timestamp())}:f>',
            inline=False,
        )

    if trans.is_executed:
        embed.add_field(
            name='Execution time',
            value=f'<t:{int(trans.execution_time.timestamp())}:f>',
            inline=False,
        )

        embed.add_field(
            name='Execution price',
            value=f'{trans.price:,.2f}',
            inline=False,
        )

        if trans.order_fee > 0:
            embed.add_field(
                name='Order fee',
                value=f'{trans.order_fee:,.2f}',
                inline=False,
            )

    elif trans.is_cancelled:
        embed.add_field(
            name='Cancelled',
            value=f'<t:{int(trans.cancelled_time.timestamp())}:f>',
            inline=False,
        )

    return embed


def create_security_embed(security: Security) -> Embed:
    embed = Embed(
        title=security.key,
        description=f'{security.price:,.2f}'
    )

    embed.set_author(
        name=security.name,
        icon_url=security.icon_url,
    )

    embed.add_field(name='ASK', value=f'{security.ask:,.2f}')
    embed.add_field(name='BID', value=f'{security.bid:,.2f}')

    return embed
