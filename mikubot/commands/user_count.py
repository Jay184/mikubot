from discord import Interaction, Embed
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='usercount', description='Number of users in server.')
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        avatar_embed = Embed(
            description=f'The guild has {interaction.guild.member_count} members',
            color=0x86cecb,
        )

        avatar_embed.set_author(name='Member Count', icon_url='https://images.gamebanana.com/img/ico/games/6296031c71087.png')
        avatar_embed.set_footer(text=bot.user.display_name)

        await interaction.response.send_message(  # noqa
            embed=avatar_embed,
        )
