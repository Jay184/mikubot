from discord import Interaction, Member, Embed
from discord.app_commands import describe, checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='it', description='Asks for basic diagnostic info.')
    @checks.bot_has_permissions(send_messages=True)
    @describe(user='Optional user to ping.')
    async def handler(interaction: Interaction, user: Member | None = None):
        embed = Embed(
            description='''\
- Your mods folder
- Eden project folder
- Contents of `config.toml` in the Eden project folder
- Right click on the Eden project folder, select properties, and screenshot the dialog window
''',
            color=0x86cecb,
        )

        if user:
            embed.description += f'\n\n{user.mention}, please provide the requested information.'

        embed.set_author(name='Send screenshots of', icon_url='https://images.gamebanana.com/img/ico/games/6296031c71087.png')
        embed.set_footer(text=bot.user.display_name)

        await interaction.response.send_message(  # noqa
            embed=embed,
        )
