import logging

logger = logging.getLogger()
logger.setLevel("INFO")

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(stream_handler)
