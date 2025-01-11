import json
import logging
from .job_progress import ComfyJob
import websocket
import time
from ..lib.utils import deep_merge, get_time_ms
import asyncio
from ..lib.messaging import (
    create_timestamped_data,
    create_status_log,
    send_ws_message,
)
from .models import (
    Input,
    ExecutionData,
    ExecutionCallbacks,
    PerformanceMetrics,
    BaseWorkerResponse,
)

logger = logging.getLogger(__name__)

# Used to indicate if comfy is already running for standard execute/run_prompt APIs.
comfy_running = False


MSG_TYPES_TO_PROCESS = [
    "executing",
    "execution_cached",
    "execution_complete",
    "execution_start",
    "progress",
    "status",
    "completed",
]


async def run_prompt(data: Input, websockets=True, on_ws_message=None):
    """
    Run a ComfyUI prompt with optional websocket support for progress monitoring.

    This function handles the complete lifecycle of prompt execution including logging,
    websocket connections, and callback management.

    Args:
        data: Input object containing prompt details and execution metadata
        websockets: Boolean flag to enable/disable websocket connection to server

    Returns:
        Dict containing execution results and metadata

    Raises:
        Exception: If there's an error during prompt execution
    """

    # Setting up custom logging handler
    server_ws_connection = None
    job_start_time = get_time_ms()

    # Initialize logging
    logger.info(f"Job ID: {data.process_id}. User ID: {data.client_id}")

    # Prepare response data structure
    to_send_back = BaseWorkerResponse(
        client_id=data.client_id,
        process_id=data.process_id,
    )

    performance_metrics = PerformanceMetrics(
        execution_time=0,
        execution_delay_time=0,
    )

    try:
        # Setup websocket connection if enabled
        if websockets and data.connection_url:  # Add check for connection_url
            logger.info(
                f"Starting server ws connection. Connection URL: {data.connection_url}"
            )
            server_connect_start_time = get_time_ms()
            server_ws_connection = websocket.WebSocket()
            server_ws_connection.connect(data.connection_url)
            server_connection_time = get_time_ms() - server_connect_start_time
            logger.info(
                f"Connected to Server. Time to connect: {server_connection_time} ms"
            )
            to_send_back.performance_metrics.server_connection_time = int(
                server_connection_time
            )
    except Exception as e:
        logger.error(f"Failed to establish websocket connection to server: {e}")
        logger.error(
            "Continuing job execution... Will return via REST API when completed.",
        )
        server_ws_connection = None

    try:
        # Define callbacks for execution monitoring
        callbacks = ExecutionCallbacks(
            on_error=lambda error_data: (
                logger.error(error_data),
                send_ws_message(
                    server_ws_connection,
                    "worker:job_failed",
                    deep_merge(
                        to_send_back,
                        {"error_message": error_data.get("exception_message", "")},
                    ),
                ),
            ),
            on_ws_message=on_ws_message,
            on_done=lambda msg: (
                setattr(
                    performance_metrics,
                    "execution_time",
                    int(get_time_ms() - job_start_time),
                ),
                send_ws_message(
                    server_ws_connection, "worker:job_completed", to_send_back
                )
                if server_ws_connection
                else None,
                logger.info(
                    f"Job Completed for: Job ID {data.process_id}. Sending Completion Event."
                ),
            ),
            on_progress=lambda event, msg, sid: (
                send_ws_message(
                    server_ws_connection,
                    "worker:job_progress",
                    {
                        **create_timestamped_data(data.process_id, data),
                        "percentage": msg.get("percentage", 0),
                    },
                )
                if server_ws_connection
                else None,
                logger.info(f"Job Progress: {msg.get('percentage', 0)}%"),
            ),
            on_start=lambda msg: (
                setattr(
                    performance_metrics,
                    "execution_delay_time",
                    int(time.time() * 1000 - job_start_time),
                ),
                logger.info(
                    f"Execution start took: {time.time()*1000 - job_start_time} ms"
                ),
            ),
        )

        # Execute the prompt
        execution_result = await execute(data=data, callbacks=callbacks)
        to_send_back.update(execution_result)

        return to_send_back

    except Exception as e:
        logger.error(f"Error in execution: {str(e)}")
        raise e
    finally:
        if server_ws_connection:
            server_ws_connection.close()


def queue_prompt(data):
    import urllib

    payload = {"prompt": data["prompt"], "client_id": data["client_id"]}
    serialized = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request("http://localhost:8188/prompt", data=serialized)

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


async def execute(
    data: ExecutionData, callbacks: ExecutionCallbacks, timeout: int = 60
):
    """
    Asynchronously execute a ComfyUI prompt with websocket-based monitoring and callbacks.

    This function queues a prompt for execution and monitors its progress via websocket,
    triggering appropriate callbacks at different stages of execution.

    Args:
        data: ExecutionData containing prompt and execution metadata
        callbacks: ExecutionCallbacks instance containing callback functions
        timeout: Maximum time to wait for execution in seconds

    Returns:
        Dict containing execution results including prompt_id and process_id

    Raises:
        Exception: If there's an error during prompt queuing or execution
        asyncio.TimeoutError: If execution exceeds timeout
    """
    global comfy_running
    if not comfy_running:
        launch_comfy(8188, gpu_only=False, wait_for_ready=True)
        comfy_running = True
    execution_started = False
    ws = None

    try:
        comfy_job = ComfyJob(data.prompt)
        queue_start_time = get_time_ms()
        queue_response = queue_prompt(
            {"prompt": data.prompt, "client_id": data.process_id}
        )
        prompt_id = queue_response["prompt_id"]
        queue_end_time = get_time_ms()
        comfy_queue_duration = queue_end_time - queue_start_time

        ws = websocket.WebSocket()
        ws.connect(f"ws://localhost:8188/ws?clientId={data.process_id}")
        result_future = asyncio.Future()

        async def monitor_ws():
            nonlocal execution_started

            while True:
                # Use asyncio.to_thread for the blocking websocket receive
                out = await asyncio.to_thread(ws.recv)
                if not isinstance(out, str):
                    continue

                message = json.loads(out)
                message_type = message.get("type", None)
                message_data = message.get("data", {})
                msg_prompt_id = message_data.get("prompt_id", None)

                # Skip irrelevant messages
                if (
                    prompt_id != msg_prompt_id
                    or message_type not in MSG_TYPES_TO_PROCESS
                    or not comfy_job
                ):
                    continue

                callbacks.on_ws_message(message_type, message_data)

                # Handle execution errors
                if message_type == "execution_error":
                    if callbacks.on_error:
                        callbacks.on_error(message.get("data", {}))
                    raise Exception(
                        message.get("data", {}).get(
                            "exception_message", "Unknown Exception"
                        )
                    )

                # Update job status
                comfy_job.addStatusLog(create_status_log(message_data, prompt_id))

                # Handle execution progress
                if message["type"] == "executing":
                    # Trigger start callback on first execution message
                    if not execution_started and callbacks.on_start:
                        callbacks.on_start({"process_id": data.process_id})
                        execution_started = True

                    if callbacks.on_progress:
                        callbacks.on_progress(
                            "progress", {"progress": comfy_job.getPercentage()}, None
                        )

                    # Check for completion
                    if message_data["node"] is None:
                        if callbacks.on_done:
                            callbacks.on_done({"process_id": data.process_id})
                        result_future.set_result(
                            {
                                "prompt_id": prompt_id,
                                "queue_duration": comfy_queue_duration,
                            }
                        )
                        break

        # Start monitoring task and wait for result with timeout
        monitor_task = asyncio.create_task(monitor_ws())
        try:
            return await asyncio.wait_for(result_future, timeout=timeout)
        except asyncio.TimeoutError:
            monitor_task.cancel()
            raise

    except Exception as e:
        if callbacks.on_error:
            callbacks.on_error({"error_message": str(e)})
        raise

    finally:
        if ws:
            ws.close()
