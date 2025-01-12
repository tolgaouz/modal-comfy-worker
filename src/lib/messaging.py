from typing import Dict, Any, Protocol, TypedDict, Literal
import websocket
from ..comfy.job_progress import ComfyStatusLog
from .json_encoder import JSONEncoder
import json
from ..lib.exceptions import WebSocketError
from .utils import get_time_ms


class JobData(Protocol):
    process_id: str
    client_id: str


class TimestampedData(TypedDict):
    timestamp: int
    prompt_id: str
    process_id: str
    client_id: str


def create_timestamped_data(prompt_id: str, data: JobData) -> TimestampedData:
    return {
        "timestamp": get_time_ms(),
        "prompt_id": prompt_id,
        "process_id": data.process_id,
        "client_id": data.client_id,
    }


def send_ws_message(
    server_ws_connection: websocket.WebSocket,
    type: Literal[
        "worker:job_failed",
        "worker:job_completed",
        "worker:job_progress",
        "worker:job_started",
    ],
    to_send_back: Any,
) -> bool:
    try:
        if server_ws_connection:
            server_ws_connection.send(
                json.dumps(
                    {
                        "type": type,
                        "data": to_send_back,
                    },
                    cls=JSONEncoder,
                )
            )
        return True
    except Exception:
        raise WebSocketError(
            "Failed to send websocket message. Websocket server may not be running"
        )
