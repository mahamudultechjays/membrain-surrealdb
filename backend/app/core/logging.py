"""Central logging configuration."""

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """Configure the root logger once, at startup."""
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
