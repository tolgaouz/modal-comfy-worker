from typing import Any, Protocol, TypedDict, Literal
import websocket
from .json_encoder import JSONEncoder
import json
from ..lib.exceptions import WebSocketError


class JobData(Protocol):
    process_id: str
    client_id: str


class TimestampedData(TypedDict):
    timestamp: int
    prompt_id: str
    process_id: str
    client_id: str


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
