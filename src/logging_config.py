"""Application logging. Detailed diagnostics go to the log, never to dashboard users."""
import logging

from src import config


def setup_logging() -> None:
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
