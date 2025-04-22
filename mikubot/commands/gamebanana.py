from discord import Interaction, Embed
from discord.app_commands import describe, checks
from mikubot import Bot
from datetime import datetime, timezone
import requests


def register(bot: Bot):
    def create_mod_embed(data: dict, full: bool = False) -> Embed:
        embed = Embed(
            title=data.get('_sName'),
            url=data.get('_sProfileUrl'),
            timestamp=datetime.fromtimestamp(data.get('_tsDateAdded'), timezone.utc),
            color=0x86cecb,
        )

        # Mark obselete
        if data.get('_bIsObsolete', False):
            embed.title = f'~~{embed.title}~~'

        embed.set_author(
            name=data.get('_aSubmitter', {}).get('_sName'),
            icon_url=data.get('_aRootCategory', {}).get('_sIconUrl')
        )

        first_image = data.get('_aPreviewMedia').get('_aImages')[0]
        first_image_url = first_image.get('_sBaseUrl') + '/' + first_image.get('_sFile')

        embed.set_thumbnail(url=first_image_url)
        embed.set_footer(text=bot.user.display_name)

        embed.add_field(
            name='Submitter',
            value=data.get('_aSubmitter', {}).get('_sName'),
            inline=True,
        )

        embed.add_field(
            name='Likes',
            value=data.get('_nLikeCount', 0),
            inline=True,
        )

        embed.add_field(
            name='Views',
            value=data.get('_nViewCount', 0),
            inline=True,
        )

        if '_aAdditionalInfo' in data and '_sversion' in data.get('_aAdditionalInfo'):
            embed.add_field(
                name='Version',
                value=data.get('_aAdditionalInfo', {}).get('_sversion', 'Unknown version'),
                inline=True,
            )

        # The following require a new API call
        if full:
            mod_id = data.get('_idRow')
            profile_url = f'https://gamebanana.com/apiv10/Mod/{mod_id}/ProfilePage'
            response = requests.get(profile_url)

            if response.status_code == 200:
                profile_data = response.json()

                if '_aContentRatings' in profile_data and len(profile_data.get('_aContentRatings', {})):
                    embed.add_field(
                        name='Content Warnings',
                        value=', '.join(profile_data.get('_aContentRatings', {}).values()),
                        inline=True,
                    )

                if '_sDescription' in profile_data:
                    embed.description = profile_data.get('_sDescription')

        return embed

    @bot.tree.command(name='gamebanana', description='Searches for a mod in the MegaMix+ section of Gamebanana.')
    @checks.bot_has_permissions(send_messages=True)
    @describe(query='The mod name or submission ID to search for.')
    async def handler(interaction: Interaction, query: str):
        settings = bot.settings.gamebanana_search

        await interaction.response.defer()  # noqa

        url = f'https://gamebanana.com/apiv10/Game/16522/Subfeed?_nPage=1&_nPerpage=10&_sSort=default&_sName={query}'
        response = requests.get(url)

        if response.status_code != 200:
            return

        results = response.json().get('_aRecords') or []

        # Limit results to N entries
        result_count = len(results)

        if result_count:
            results = results[:settings.limit]

            embeds = [create_mod_embed(result, settings.full) for result in results]
            await interaction.followup.send(f'Found {result_count} results...', embeds=embeds)  # noqa
        else:
            embed = Embed(
                title='No results found.',
                color=0xffc526,
            )

            embed.set_author(name='GameBanana Search', icon_url='https://images.gamebanana.com/static/img/mascots/detective.png')
            embed.set_footer(text=bot.user.display_name)

            await interaction.followup.send(embed=embed)  # noqa
