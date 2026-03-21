from .config import Settings
from .discord import Bot
from .logger import setup_logger


def main() -> None:
    settings = Settings.load()

    if settings.discord_key:
        setup_logger(settings.logging)
        client = Bot(settings)
        client.run(settings.discord_key)


if __name__ == "__main__":
    main()
