import logging
import sys


def setup_logger(name: str = "") -> logging.Logger:
    """Configure and return a logger with consistent formatting"""
    # Get root logger to capture all messages
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplicates
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)

    # Create handler with formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    # Add handler to root logger
    logger.addHandler(handler)

    # Configure specific loggers to suppress
    logging.getLogger("hpack").setLevel(logging.WARNING)

    # Ensure propagation is enabled (default is True)
    logger.propagate = True

    return logger


logger = setup_logger()
