"""Console trace logging: one tagged key=value line per event, no persistence."""

import logging

_logger = logging.getLogger("membrain.trace")


def format_event(tag: str, **fields: object) -> str:
    """'[CAPTURE]', scope='a', cost=1 -> '[CAPTURE] scope=a cost=1'. None fields are dropped."""
    parts = [tag, *(f"{name}={value}" for name, value in fields.items() if value is not None)]
    return " ".join(parts)


def log(tag: str, **fields: object) -> None:
    _logger.info(format_event(tag, **fields))
