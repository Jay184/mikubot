from typing import Type
from discord import Interaction
from discord.app_commands import describe, checks
from mikubot import Bot, modals
import enum


class SettingsCategories(enum.Enum):
    general = modals.GeneralSettingsModal
    triggerwords = modals.TriggerWordModal
    renamechat1 = modals.RenameChatModal1
    renamechat2 = modals.RenameChatModal2
    brazil = modals.BrazilModal
    gamebanana = modals.GamebananaSearchModal
    uwufy = modals.UwufyModal
    zoe = modals.ZoeQuoteModal


def register(bot: Bot):
    @bot.tree.command(name='settings', description='Set bot settings.')
    @checks.has_permissions(administrator=True)
    @describe(category='Settings category.')
    async def handler(interaction: Interaction, category: SettingsCategories = SettingsCategories.general):
        modal_type: Type[modals.SettingsModal] = category.value
        modal = modal_type(bot)
        await interaction.response.send_modal(modal)  # noqa

    @handler.error
    async def error_handler(interaction: Interaction, error):
        await interaction.response.send_message(  # noqa
            str(error),
            ephemeral=True,
        )
