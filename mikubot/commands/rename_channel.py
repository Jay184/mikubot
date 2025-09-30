from discord import Interaction
from discord.app_commands import describe, checks, AppCommandError, CommandOnCooldown
from loguru import logger
from mikubot import Bot
import random
import asyncio


def register(bot: Bot):
    @bot.tree.command(name="renamechannel", description="1 in 50 chance to rename the spam channel, otherwise send user to Brazil.")
    @checks.bot_has_permissions(send_messages=True, manage_channels=True)
    @checks.has_role(bot.settings.brazil.member_role_id)
    @checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
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

        is_special = interaction.user.get_role(settings.special_role_id)

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
            with bot.storage("brazil", autocommit=True) as db:
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

        # Retrieval logic
        delay = settings.random_delay()

        await asyncio.sleep(delay)

        async with interaction.channel.typing():
            await interaction.user.remove_roles(brazil_role)
            await interaction.user.add_roles(member_role)

            if is_special:
                await interaction.user.remove_roles(special_brazil_role)
                await interaction.user.add_roles(special_role)

            if len(settings.retrieval_messages):
                retrieval_message = random.choice(settings.retrieval_messages).format(
                    user=interaction.user.mention,
                    delay=int(delay // 60.0),
                )

                if settings.single_message:
                    new_content = f"{fail_message}\n────────────────────────────────────────\n{retrieval_message}"
                    message = await interaction.original_response()
                    await message.edit(content=new_content)
                else:
                    await interaction.channel.send(
                        retrieval_message,
                        delete_after=None if settings.keep_messages else settings.deletion_delay,
                    )

    @handler.error
    async def error_handler(interaction: Interaction, error: AppCommandError):
        if isinstance(error, CommandOnCooldown):
            await interaction.response.send_message(  # noqa
                f"{round(error.retry_after, 2)} seconds left"
            )

        logger.exception(error)
