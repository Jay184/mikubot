from loguru import logger
import logging
import sys

from .config import LoggingSettings


class InterceptHandler(logging.Handler):
    """Intercepts the standard logging module and replaces log messages with loguru logs."""
    loglevel_mapping = {
        50: "CRITICAL",
        40: "ERROR",
        30: "WARNING",
        20: "INFO",
        10: "DEBUG",
        0: "NOTSET",
    }

    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except AttributeError:
            level = self.loglevel_mapping[record.levelno]

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        log = logger.bind(request_id="app")
        log.opt(
            depth=depth,
            exception=record.exc_info
        ).log(level, record.getMessage())


def setup_logger(settings: LoggingSettings):
    logger.level("VERBOSE", no=15, color="<blue>")

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.level.upper(),
        enqueue=True,
        colorize=True,
        backtrace=settings.backtrace,
        diagnose=settings.diagnose,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
    )

    logger.add(
        settings.file_path,
        rotation=settings.rotation,
        retention=settings.retention,
        compression="zip",
        level=settings.level.upper(),
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
