import logging
import sys
from typing import Final


def setup_logger(name: str = "") -> logging.Logger:
    """Configure and return a logger with consistent formatting"""
    logger: Final[logging.Logger] = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)

    return logger


logger = setup_logger("comfy_worker")
