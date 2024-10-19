import json
import threading
import urllib
import subprocess
import socket
from ..utils.logger import logger
from .job_progress import ComfyJobProgress, ComfyStatusLog
from ..json_encoder import JSONEncoder
import websocket
import os
from pydantic import BaseModel
from typing import Optional, Literal
from ..utils.utils import deep_merge, get_time_ms

HOST = "127.0.0.1"
PORT = "8188"
COMFY_URL = f"{HOST}:{PORT}"
CLIENT_ID_WS_CONNECTIONS = dict()


message_types_to_process = [
    "executing",
    "execution_cached",
    "progress",
]


def queue_prompt(data):
    payload = {"prompt": data["prompt"], "client_id": data["client_id"]}
    serialized = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://{COMFY_URL}/prompt", data=serialized)

    try:
        response = urllib.request.urlopen(req)
        return json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code == 400:
            error_data = json.loads(e.read())
            raise ValueError(
                f"Comfy error: {error_data.get('error', 'Unknown error')}, Node errors: {error_data.get('node_errors', {})}"
            )
        else:
            raise Exception("Error while queueing prompt.")


def get_comfy_websocket(client_id):
    ws = CLIENT_ID_WS_CONNECTIONS.get(client_id)
    if not ws:
        ws = websocket.WebSocket()
        ws.connect(f"ws://{COMFY_URL}/ws?clientId={client_id}")
        print(
            f"comfy-modal - connected to websocket at {COMFY_URL} with client_id {client_id}"
        )
        CLIENT_ID_WS_CONNECTIONS[client_id] = ws
    else:
        print(
            "comfy-modal - reusing existing websocket connection for client id:",
            client_id,
        )
    return ws


def create_status_log(message_data, prompt_id):
    return ComfyStatusLog(
        prompt_id=prompt_id,
        node=message_data.get("node", None),
        status=message_data.get("status", None),
        max=message_data.get("max", 1),
        value=message_data.get("value", 1),
        nodes=message_data.get("nodes", []),
    )


def launch_comfy(port=PORT, gpu_only=True, wait_for_ready=True):
    cmd = [
        "python",
        "/root/ComfyUI/main.py",
        "--dont-print-server",
        "--disable-auto-launch",
        "--disable-metadata",
        "--listen",
    ]
    if gpu_only:
        cmd.append("--gpu-only")
    if port:
        cmd.append("--port")
        cmd.append(str(port))
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    threading.Thread(
        target=_log_comfy, args=("STDOUT", process.stdout), daemon=True
    ).start()
    threading.Thread(
        target=_log_comfy, args=("STDERR", process.stderr), daemon=True
    ).start()

    # Poll until webserver accepts connections before running inputs.
    if wait_for_ready:
        while True:
            try:
                socket.create_connection((HOST, int(PORT)), timeout=1).close()
                print("ComfyUI webserver ready!")
                break
            except (socket.timeout, ConnectionRefusedError):
                retcode = process.poll()
                if retcode is not None:
                    raise RuntimeError(
                        f"comfyui main.py exited unexpectedly with code {retcode}"
                    )
        return True


def _log_comfy(pipe):
    for line in iter(pipe.readline, ""):
        logger.info(f"COMFY - {line.strip()}")
    pipe.close()


def send_socket_message(
    server_ws_connection: Optional[websocket.WebSocket],
    type: Literal["job_failed", "job_completed", "job_progress"],
    data: dict,
):
    try:
        if server_ws_connection:
            server_ws_connection.send(
                json.dumps(
                    {
                        "type": type,
                        "data": data,
                    },
                    cls=JSONEncoder,
                )
            )
    except Exception as e:
        logger.warning("Failed to send job failed message for")
        logger.warning(e)
        return False


class ProcessJobInput(BaseModel):
    prompt: dict
    client_id: str
    job_id: str
    ws_connection_url: Optional[str] = ""


def process_job(data: ProcessJobInput):
    execution_started = False
    server_ws_connection = None
    job_start_time = get_time_ms()
    to_send_back = {
        "process_id": data.process_id,
        "client_id": data.client_id,
        "provider_metadata": {
            "region": os.environ.get("MODAL_REGION", "Unknown"),
            "cloud_provider": os.environ.get("MODAL_CLOUD_PROVIDER", "Unknown"),
            "container_id": os.environ.get("MODAL_TASK_ID", "Unknown"),
        },
    }
    if data.ws_connection_url:
        try:
            logger.info(
                "Starting server ws connection. Connection URL: "
                + data.ws_connection_url
            )
            server_connect_start_time = get_time_ms()
            server_ws_connection = websocket.WebSocket()
            server_ws_connection.connect(data.ws_connection_url)
            server_connection_time = get_time_ms() - server_connect_start_time
            logger.info(
                f"Connected to Server. Time to connect: {server_connection_time} ms"
            )
            to_send_back["server_connection_time"] = server_connection_time
        except Exception as e:
            logger.warning(f"Failed to establish websocket connection to server: {e}")
            logger.warning(
                "Continuing job execution... Will return via REST API when completed."
            )
            # Dont break the job, just log the error and move on
    try:
        comfy_job = ComfyJobProgress(data.prompt)
        queue_response = queue_prompt(
            {"prompt": data.prompt, "client_id": data.client_id}
        )
        prompt_id = queue_response["prompt_id"]
        logger.info(f"Queued Workflow with ID: {prompt_id} for Job ID: {data.job_id}")
        ws = get_comfy_websocket(data.client_id)
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                message_data = message.get("data", {})
                msg_prompt_id = message_data.get("prompt_id", None)
                if (
                    prompt_id != msg_prompt_id
                    or message.get("type", None) not in message_types_to_process
                    or not comfy_job
                ):
                    continue
                if message.get("type", None) in [
                    "execution_error",
                    "exception_message",
                ]:
                    raise Exception("Unexpected error while generating output.")
                comfy_job.addStatusLog(create_status_log(message_data, prompt_id))
                if message["type"] == "executing":
                    if execution_started is False:
                        execution_start_time = get_time_ms()
                        execution_start_delay = execution_start_time - job_start_time
                        logger.info(
                            f"Time to start execution: {execution_start_delay} ms"
                        )
                        to_send_back["execution_delay_time"] = execution_start_delay
                        send_socket_message(
                            server_ws_connection,
                            "job_started",
                            to_send_back,
                        )
                        execution_started = True
                    send_socket_message(
                        server_ws_connection,
                        "job_progress",
                        deep_merge(
                            to_send_back, {"percentage": comfy_job.get_progress_data()}
                        ),
                    )
                    if message_data["node"] is None:
                        to_send_back["execution_time"] = (
                            get_time_ms() - execution_start_time
                        )
                        send_socket_message(
                            server_ws_connection,
                            "job_completed",
                            to_send_back,
                        )
                        logger.info(
                            f"Job Completed for: Prompt ID {prompt_id} - Process ID {data.job_id}. Sending Completion Event. Message: {message}"
                        )
                        break
        return to_send_back
    except Exception as e:
        logger.error(f"Comfy Processing Exception - Comfy Error Message: {e}")
        failed_data = deep_merge(to_send_back, {"error_message": str(e)})
        send_socket_message(server_ws_connection, "job_failed", failed_data)
        return failed_data
    finally:
        job_end_time = get_time_ms()
        job_duration = job_end_time - job_start_time
        logger.info(f"Total job duration: {job_duration} ms")
