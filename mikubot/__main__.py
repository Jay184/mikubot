from .config import Settings
from .discord import Bot
from .logger import setup_logger


if __name__ == '__main__':
    settings = Settings.load()

    if settings.discord_key:
        setup_logger()
        client = Bot(settings)
        client.run(settings.discord_key)
