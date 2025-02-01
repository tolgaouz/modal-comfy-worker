import time
import os


def get_time_ms() -> int:
    return int(round(time.time() * 1000))


def check_disk_speed():
    """
    Check the disk speed of the current machine.
    """
    test_size = 1024 * 1024 * 100  # 100MB
    test_file = "/tmp/speedtest"

    # Write speed test
    start = time.time()
    with open(test_file, "wb") as f:
        f.write(b"0" * test_size)
    write_speed = test_size / (time.time() - start) / (1024 * 1024)  # MB/s

    # Read speed test
    start = time.time()
    with open(test_file, "rb") as f:
        f.read()
    read_speed = test_size / (time.time() - start) / (1024 * 1024)  # MB/s

    os.remove(test_file)
    return read_speed, write_speed
