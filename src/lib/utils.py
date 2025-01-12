import time


def get_time_ms() -> int:
    return int(round(time.time() * 1000))
