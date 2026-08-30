import logging
import os


def get_logger(name: str) -> logging.Logger:
    """Return a consistently configured logger for an application module.

    Args:
        name: Logger name, normally ``__name__`` from the caller.

    Returns:
        A standard-library logger configured from ``LOG_LEVEL``.
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger(name)
