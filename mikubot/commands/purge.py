from discord import Interaction, Embed
from discord.app_commands import describe, checks, Range
from mikubot import Bot
from datetime import datetime, timezone


def register(bot: Bot):
    @bot.tree.command(name='purge', description='Deletes the last N messages in the channel.')
    @checks.has_permissions(manage_messages=True)
    @checks.bot_has_permissions(send_messages=True)
    @describe(count='The number of messages to delete (max 100).')
    async def handler(interaction: Interaction, count: Range[int, 1, 100]):
        messages = [m async for m in interaction.channel.history(limit=count)]
        await interaction.channel.delete_messages(messages)

        embed = Embed(
            title='Purged Messages',
            description=f'Deleted {count} messages.',
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc),
        )

        embed.set_footer(text=bot.user.display_name)

        await interaction.response.send_message(  # noqa
            embed=embed,
            delete_after=5.0,
        )
