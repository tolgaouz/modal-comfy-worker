from typing import Dict, Any, Protocol, TypedDict
import websocket
from ..comfy.job_progress import ComfyStatusLog
from .json_encoder import JSONEncoder
import json
from .logger import logger
from .utils import get_time_ms
from .constants import WS_MESSAGE_TYPE


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


def create_status_log(message_data: Dict[str, Any], prompt_id: str) -> ComfyStatusLog:
    return ComfyStatusLog(
        prompt_id=prompt_id,
        node=message_data.get("node", None),
        status=message_data.get("status", None),
        max=message_data.get("max", 1),
        value=message_data.get("value", 1),
        nodes=message_data.get("nodes", []),
    )


def send_ws_message(
    server_ws_connection: websocket.WebSocket,
    type: WS_MESSAGE_TYPE,
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
    except Exception as e:
        client_id = to_send_back.get("client_id", None)
        process_id = to_send_back.get("process_id", None)
        if client_id and process_id:
            logger.error(f"Failed to send websocket message for {process_id}")
            logger.error(str(e))
        return False
