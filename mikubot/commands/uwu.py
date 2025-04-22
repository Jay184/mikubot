from discord import Interaction, Message, TextChannel
from discord.app_commands import describe, checks
from uwuipy import Uwuipy
from mikubot import Bot


def register(bot: Bot):
    def create_uwufier(channel: TextChannel) -> Uwuipy:
        settings = bot.settings.uwufy
        nsfw = settings.nsfw_actions or channel.id in settings.nsfw_channels

        return Uwuipy(
            stutter_chance=settings.stutter_chance,
            face_chance=settings.face_chance,
            action_chance=settings.action_chance,
            exclamation_chance=settings.exclamation_chance,
            nsfw_actions=nsfw,
            power=settings.power,
        )

    @bot.tree.command(name='uwu', description='Uwu-ify your text!')
    @checks.bot_has_permissions(send_messages=True)
    @describe(text='The text you want to uwu-ify.')
    async def handler(interaction: Interaction, text: str):
        text = create_uwufier(interaction.channel).uwuify(text)
        await interaction.response.send_message(text, allowed_mentions=None)  # noqa

    @bot.tree.context_menu(name='uwufy')
    @checks.bot_has_permissions(send_messages=True)
    async def context_handler(interaction: Interaction, message: Message):
        text = create_uwufier(interaction.channel).uwuify(message.content)
        await interaction.response.send_message(text, allowed_mentions=None)  # noqa
