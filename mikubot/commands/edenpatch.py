from discord import Interaction, Embed
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='edenpatch', description='Info on songlimit patch, song id patch, etc.')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        embed = Embed(
            description=r'The Eden \_\_\_\_\_\_\_ Patch series of mods are public releases of mods that are included within Eden Project and as a result can cause some unintended side effects when enabled with Eden Project, as the mods are effectively running twice.',
            color=0x86cecb,
        )

        embed.set_author(name='Eden Patch', icon_url='https://images.gamebanana.com/img/ico/games/6296031c71087.png')
        embed.set_footer(text=bot.user.display_name)

        await interaction.response.send_message(  # noqa
            embed=embed,
        )
