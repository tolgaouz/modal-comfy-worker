from typing import Final, Literal

# WebSocket message types
WS_MESSAGE_TYPE = Literal[
    "worker:job_failed",
    "worker:job_completed",
    "worker:job_progress",
    "worker:job_started",
]
WS_MESSAGE_TYPES: Final[list[WS_MESSAGE_TYPE]] = [
    "worker:job_failed",
    "worker:job_completed",
    "worker:job_progress",
    "worker:job_started",
]

# Time format
TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%SZ"
