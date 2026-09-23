import sys
from loguru import logger


def setup_logging(log_file: str | None = None, level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    if log_file:
        logger.add(log_file, level="DEBUG", rotation="10 MB", encoding="utf-8")
