from modal import Secret, enter, App, web_endpoint, Volume, web_server
from ...lib.exceptions import WebSocketError
from ...comfy.server import ComfyServer, ComfyConfig
from ...lib.image import get_comfy_image
from ...comfy.models import ExecutionData, ExecutionCallbacks
import websocket
from ...lib.logger import logger
from ...lib.messaging import send_ws_message
from ...lib.utils import get_time_ms
import os

local_snapshot_path = os.path.join(os.path.dirname(__file__), "snapshot.json")

github_secret = Secret.from_name("github-secret")

image = get_comfy_image(local_snapshot_path, github_secret)

APP_NAME = "comfy-flux-ws"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)
volume = Volume.from_name(VOLUME_NAME, create_if_missing=True)


class WebsocketsRunInput(ExecutionData):
    ws_connection_url: str


@app.cls(
    image=image,
    # Add in your secrets
    secrets=[],
    # Add in your volumes
    volumes={"/root/ComfyUI/models": volume},
    gpu="l4",
    # allow_concurrent_inputs=3,
    # concurrency_limit=10,
    # timeout=38,
    container_idle_timeout=60 * 2,
    # keep_warm=1,
    retries=3,
)
class ComfyWorkflow:
    @enter()
    def run_this_on_container_startup(self):
        self.server = ComfyServer()
        self.server.start()
        self.server.wait_until_ready()

    @web_endpoint(method="POST")
    async def infer(self, data: WebsocketsRunInput):
        server_ws_connection = None
        job_start_time = get_time_ms()

        # Initialize logging
        logger.info(f"Job ID: {data.process_id}. User ID: {data.client_id}")

        try:
            # Setup websocket connection if enabled
            if data.ws_connection_url:
                logger.info(
                    f"Starting server ws connection. Connection URL: {data.ws_connection_url}"
                )
                server_connect_start_time = get_time_ms()
                server_ws_connection = websocket.WebSocket()
                server_ws_connection.connect(data.ws_connection_url)
                server_connection_time = get_time_ms() - server_connect_start_time
                logger.info(
                    f"Connected to Server. Time to connect: {server_connection_time} ms"
                )
        except Exception:
            raise WebSocketError(
                "Failed to establish websocket connection to server: {e}"
            )

        try:
            # Define callbacks for execution monitoring
            callbacks = ExecutionCallbacks(
                on_error=lambda error_data: (
                    logger.error(error_data),
                    send_ws_message(
                        server_ws_connection,
                        "worker:job_failed",
                        {
                            "error_message": error_data.get(
                                "exception_message",
                                "Unexpected exception while executing the workflow",
                            )
                        },
                    ),
                ),
                on_done=lambda msg: (
                    send_ws_message(
                        server_ws_connection,
                        "worker:job_completed",
                        {"process_id": data.process_id},
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
                            "percentage": msg.get("percentage", 0),
                        },
                    )
                    if server_ws_connection
                    else None,
                    logger.info(f"Job Progress: {msg.get('percentage', 0)}%"),
                ),
                on_start=lambda msg: (
                    logger.info(
                        f"Execution start took: {get_time_ms() - job_start_time} ms"
                    ),
                ),
            )

            # Execute the prompt
            execution_result = await self.server.execute(data=data, callbacks=callbacks)

            return execution_result
        except Exception as e:
            logger.error(f"Error in execution: {str(e)}")
            raise e
        finally:
            if server_ws_connection:
                server_ws_connection.close()


@app.function(
    allow_concurrent_inputs=10,
    concurrency_limit=1,
    image=image,
    volumes={"/root/ComfyUI/models": volume},
    container_idle_timeout=30,
    timeout=1800,
    gpu="l4",
)
@web_server(8188, startup_timeout=120)
def ui():
    logger.info("Starting UI")
    config = ComfyConfig(SERVER_HOST="0.0.0.0", SERVER_PORT=8188)
    server = ComfyServer(config=config)
    server.start()
