
import logging
import sys

logger = logging.getLogger("multiuser_repost_bot")


def setup_logging(level: str = "INFO") -> None:
    if logger.handlers:
        return
    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logging.getLogger("aiogram").setLevel(level)
    logging.getLogger("telethon").setLevel(level)
