from discord import Interaction, Message
from discord.app_commands import describe, checks
from googletrans import Translator
from googletrans.constants import LANGUAGES

from mikubot import Bot
import random
import asyncio


async def safe_translate(translator: Translator, text: str, src: str, dest: str, retries: int = 3) -> str:
    """Translate text with retries and delay on failure."""
    for attempt in range(retries):
        try:
            translated = await translator.translate(text, src=src, dest=dest)
            return translated.text
        except Exception as e:  # noqa
            if attempt < retries - 1:
                await asyncio.sleep(1 + attempt)  # wait longer each retry
            else:
                # Give up, return what we have so far
                return text
    return text


async def mass_translate(text: str, hops: int = 10, initial_lang: str = "en", final_lang: str = "en") -> str:
    current_text = text
    hops = max(0, hops)

    available_langs = list(LANGUAGES.keys())

    if initial_lang in available_langs:
        available_langs.remove(initial_lang)

    if final_lang in available_langs:
        available_langs.remove(final_lang)

    async with Translator() as translator:
        for _ in range(hops):
            random_lang = random.choice(available_langs)
            current_text = await safe_translate(translator, current_text, src=initial_lang, dest=random_lang)
            initial_lang = random_lang
            await asyncio.sleep(random.uniform(0.5, 1.5))  # small delay to reduce rate limit risk

        current_text = await safe_translate(translator, current_text, src=initial_lang, dest=final_lang)

    return current_text


def register(bot: Bot):
    @bot.tree.command(name="jumble", description="Google translates text through random languages before returning to the original language.")
    @checks.cooldown(1, 10, key=lambda i: (i.guild_id,))
    @checks.bot_has_permissions(send_messages=True)
    @describe(
        text="The text to translate",
        hops="How many languages to translate to",
        initial_lang="Language to start with",
        final_lang="Language to end on",
    )
    async def handler(interaction: Interaction, text: str, hops: int = 10, initial_lang: str = "en", final_lang: str = "en"):
        await interaction.response.defer()  # noqa
        text = await mass_translate(text, hops, initial_lang, final_lang)
        await interaction.followup.send(text[:2000])  # noqa

    @bot.tree.context_menu(name="jumble")
    @checks.bot_has_permissions(send_messages=True)
    async def context_handler(interaction: Interaction, message: Message):
        # We could use discord.py's modals to query for hops and languages if we need to.
        hops = 10
        initial_lang = "en"
        final_lang = "en"

        await interaction.response.defer()  # noqa
        text = await mass_translate(message.content, hops, initial_lang, final_lang)
        await interaction.followup.send(text[:2000], allowed_mentions=None)  # noqa
