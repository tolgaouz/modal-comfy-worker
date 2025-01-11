import time
from typing import Literal
import websocket
from ..comfy.job_progress import ComfyStatusLog
from .json_encoder import JSONEncoder
import json
from .logger import logger


def create_timestamped_data(prompt_id, data):
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt_id": prompt_id,
        "process_id": data.process_id,
        "client_id": data.client_id,
    }


def create_status_log(message_data, prompt_id):
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
    type: Literal["worker:job_failed", "worker:job_completed", "worker:job_progress"],
    to_send_back: dict,
):
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
    except Exception as e:
        client_id = to_send_back.get("client_id", None)
        process_id = to_send_back.get("process_id", None)
        if client_id and process_id:
            logger.error(f"Failed to send websocket message for {process_id}")
            logger.error(str(e))
        return False
