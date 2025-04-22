from discord import Interaction, Embed, Member
from discord.app_commands import describe, checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='avatar', description='Get the avatar of a user.')
    @checks.bot_has_permissions(send_messages=True)
    @describe(user='The user to retrieve the avatar of.')
    async def handler(interaction: Interaction, user: Member):
        embed = Embed(
            title=f'{user.name}\'s Avatar',
            color=0x0099ff,
        )

        embed.set_footer(text=bot.user.display_name)
        embed.set_image(url=user.display_avatar.url)

        await interaction.response.send_message(  # noqa
            embed=embed,
            ephemeral=True,
        )
