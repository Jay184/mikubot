from discord import Interaction
from discord.app_commands import checks
from loguru import logger
from mikubot import Bot
from mikubot.config import ReplyCommandConfig


def register_reply_command(bot: Bot, command: ReplyCommandConfig):
    @bot.tree.command(name=command.name, description=command.description)
    @checks.bot_has_permissions(send_messages=True)
    async def handler(interaction: Interaction):
        await interaction.response.send_message(  # noqa
            command.text,
            ephemeral=command.ephemeral,
        )


def register(bot: Bot):
    commands = [c for c in bot.settings.reply_commands if c.enabled]

    for command in commands:
        logger.info(f"Registering reply-command {command.name}: {command.description}.")
        register_reply_command(bot, command)
