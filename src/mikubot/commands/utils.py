from discord import Interaction
from discord.app_commands import errors, checks


def format_minutes(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    parts = []

    if hours:
        parts.append(f"{hours} hour{"s" if hours != 1 else ""}")

    if minutes or not parts:
        parts.append(f"{minutes} minute{"s" if minutes != 1 else ""}")

    return " ".join(parts)


def is_admin_or_owner(owner_id: int | None = None):
    def predicate(interaction: Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True

        if owner_id and interaction.user.id == owner_id:
            return True

        raise errors.CheckFailure("You do not have permission to use this command.")

    return checks.check(predicate)
