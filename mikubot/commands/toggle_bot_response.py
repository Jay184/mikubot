from discord import Interaction
from discord.app_commands import checks
from mikubot import Bot


def register(bot: Bot):
    @bot.tree.command(name='togglebotresponse', description='Toggle the bot responding to trigger words in your messages.')
    @checks.bot_has_permissions(send_messages=True, manage_roles=True)
    async def handler(interaction: Interaction):
        ignored_role = await interaction.guild.fetch_role(bot.settings.trigger_words.ignored_role_id)

        existing_role = interaction.user.get_role(ignored_role.id)

        if existing_role:
            await interaction.user.remove_roles(ignored_role)
            reply_text = 'The role has been removed, and the bot will now respond to your messages.'
        else:
            await interaction.user.add_roles(ignored_role)
            reply_text = 'The role has been added, and the bot will no longer respond to your messages.'

        await interaction.response.send_message(reply_text, ephemeral=True)  # noqa
