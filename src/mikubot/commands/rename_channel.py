from datetime import datetime, timezone, timedelta
from discord import Interaction, Member, Guild, Role, ForumChannel, TextChannel, CategoryChannel
from discord.ext import tasks
from discord.app_commands import describe, checks
from loguru import logger
from mikubot import Bot
import random
import asyncio

from .utils import format_minutes


async def release_from_brazil(
        bot: Bot,
        channel: ForumChannel | TextChannel | CategoryChannel,
        member: Member,
        old_roles: list[Role],
        new_roles: list[Role],
        message_id: int,
        delay: int,
):
    async with channel.typing():
        await member.remove_roles(*new_roles)
        await member.add_roles(*old_roles)

        if retrieval_message := bot.settings.rename_chat.random_retrieval_message():
            delay_minutes = int(delay // 60.0)

            retrieval_message = retrieval_message.format(
                user=member.mention,
                delay=delay_minutes,
                delay_text=format_minutes(delay_minutes),
            )

            if bot.settings.rename_chat.single_message:
                message = await channel.fetch_message(message_id)
                new_content = f"{message.content}\n────────────────────────────────────────\n{retrieval_message}"
                await message.edit(content=new_content)
            else:
                await channel.send(
                    retrieval_message,
                    delete_after=None if bot.settings.rename_chat.keep_messages else bot.settings.rename_chat.deletion_delay,
                )


def register(bot: Bot):
    @tasks.loop(minutes=1.0)
    async def free_due_vacationers():
        now = datetime.now(timezone.utc).timestamp()
        channel_id = bot.settings.rename_chat.target_channel_id

        cache = {"channels": {}, "guilds": {}, "members": {}, "roles": {}}

        async def get_or_fetch(cache_dict: dict, fetch_fn: callable, k):
            """Get from cache or fetch and store."""
            if k in cache_dict:
                return cache_dict[k]
            item = await fetch_fn(k)
            cache_dict[k] = item
            return item

        async def resolve_role(g: Guild, role_id: int) -> Role:
            return await get_or_fetch(cache["roles"], g.fetch_role, role_id)

        with bot.storage(table="brazil_vacationers") as db:
            for key, data in db.items():
                end = data.get("end") or 0

                if now < end:
                    continue

                guild_id, user_id = map(int, key.split(":"))

                guild = await get_or_fetch(cache["guilds"], bot.fetch_guild, guild_id)
                member = await get_or_fetch(cache["members"], guild.fetch_member, user_id)
                channel = await get_or_fetch(cache["channels"], bot.fetch_channel, channel_id)

                old_roles = [await resolve_role(guild, rid) for rid in data.get("old_roles", [])]
                new_roles = [await resolve_role(guild, rid) for rid in data.get("new_roles", [])]

                logger.info(f"Releasing {member.display_name} from Brazil...")
                await release_from_brazil(bot, channel, member, old_roles, new_roles, data.get('message'), data.get("delay"))
                del db[key]

            db.commit()

    free_due_vacationers.start()

    @bot.tree.command(name="renamechannel", description="1 in 50 chance to rename the spam channel, otherwise send user to Brazil.")
    @checks.bot_has_permissions(send_messages=True, manage_channels=True)
    @checks.has_role(bot.settings.brazil.member_role_id)
    @checks.cooldown(1.0, 3.0, key=lambda i: (i.guild_id, i.user.id))
    @describe(newname="New channel name if successful.")
    async def handler(interaction: Interaction, newname: str):
        settings = bot.settings.rename_chat
        brazil = bot.settings.brazil

        target_channel = interaction.guild.get_channel(settings.target_channel_id)
        loading_role = interaction.guild.get_role(settings.loading_role_id)
        brazil_role = interaction.guild.get_role(brazil.brazil_role_id)
        special_role = interaction.guild.get_role(settings.special_role_id)
        special_brazil_role = interaction.guild.get_role(brazil.special_brazil_role_id)
        member_role = interaction.guild.get_role(brazil.member_role_id)

        # Only allow in spam channel
        if interaction.channel != target_channel:
            await interaction.response.send_message(f"This command can only be executed in the spam channel: <#{settings.target_channel_id}>.", ephemeral=True)  # noqa
            return

        # Abort if user has the `rolling` role
        if interaction.user.get_role(settings.loading_role_id):
            await interaction.response.send_message("You are already rolling.", ephemeral=True)  # noqa
            return

        is_special = interaction.user.get_role(settings.special_role_id) is not None

        await interaction.user.add_roles(loading_role)

        async with interaction.channel.typing():
            await interaction.response.send_message("🎲 Rolling a random number.", ephemeral=settings.ephemeral_messages)  # noqa
            message = await interaction.original_response()

            await asyncio.sleep(settings.roll_time / 3.0)
            await message.edit(content="🎲 Rolling a random number..")  # noqa
            await asyncio.sleep(settings.roll_time / 3.0)
            await message.edit(content="🎲 Rolling a random number...")  # noqa
            await asyncio.sleep(settings.roll_time / 3.0)

            rolled = random.random()
            success = rolled < settings.success_chance
            rolled = int(rolled / settings.success_chance) + 1

            # Check banned words
            if settings.contains_banned(newname):
                if success:
                    rolled = int(1.0 / settings.success_chance)

                success = False
                logger.info(f"{interaction.user.display_name} used a bad word to rename the channel.")

            if success:
                # Rename channel
                with bot.storage("brazil", autocommit=True) as db:
                    postfix = settings.lowest_postfix(db.get("streak", 0)) or "."

                    # Reset fail streak
                    db["streak"] = 0

                await target_channel.edit(name=newname)

                rename_message = f"🎉 The channel has been renamed to **{newname}** by {interaction.user.mention}! They rolled {rolled}{postfix}"
                await message.edit(content=rename_message)  # noqa
                await interaction.user.remove_roles(loading_role)

                if not settings.keep_messages:
                    await message.delete(delay=settings.deletion_delay)

                return

            # Failure
            new_role = special_brazil_role if is_special else brazil_role

            # Save streak counter
            with bot.storage(table="brazil", autocommit=True) as db:
                current_streak = db.get("streak", 0) + 1
                db["streak"] = current_streak

            fail_message = f"<:PokeOff:1274829050648465428> {interaction.user.mention} will be sent to Brazil! They rolled {rolled}."
            fail_message_postfix = f"\n{current_streak} failed rolls in a row!"

            if current_streak > 8:
                fail_message += fail_message_postfix

            await message.edit(content=fail_message)  # noqa
            await asyncio.sleep(settings.failure_delay)
            await interaction.user.add_roles(new_role)
            await interaction.user.remove_roles(member_role, loading_role)

            if is_special:
                await interaction.user.remove_roles(special_role)

            fail_message = f"<:PokeOff:1274829050648465428> {interaction.user.mention} has been sent to Brazil! They rolled {rolled}."

            if current_streak > 8:
                fail_message += fail_message_postfix

            await message.edit(content=fail_message)  # noqa

            if not settings.keep_messages:
                await message.delete(delay=settings.deletion_delay)

            delay = settings.random_delay()

            # Store user
            with bot.storage(table="brazil_vacationers") as db:
                now = datetime.now(timezone.utc)

                old_roles = [brazil.member_role_id]
                new_roles = [brazil.brazil_role_id]

                if is_special:
                    old_roles.append(settings.special_role_id)
                    new_roles.append(brazil.special_brazil_role_id)

                db[f"{interaction.guild_id}:{interaction.user.id}"] = {
                    "delay": delay,
                    "start": now.timestamp(),
                    "end": (now + timedelta(seconds=delay)).timestamp(),
                    "special": is_special,
                    "old_roles": old_roles,
                    "new_roles": new_roles,
                    "message": message.id,
                }

                db.commit()
