import subprocess
import time
import logging
import requests
import threading
from .config import ComfyConfig
from ..lib.utils import get_time_ms
from ..lib.exceptions import ServerStartupError
from .models import ExecutionResult, QueuePromptData
import json
import asyncio
import websocket
from .models import ExecutionData, ExecutionCallbacks
from .job_progress import ComfyJobProgress, ComfyStatusLog
from ..lib.exceptions import ExecutionError

logger = logging.getLogger(__name__)


class ComfyServer:
    """Manages ComfyUI server lifecycle."""

    MSG_TYPES_TO_PROCESS = [
        "executing",
        "execution_cached",
        "execution_complete",
        "execution_start",
        "progress",
        "status",
        "completed",
    ]

    def __init__(self, config: ComfyConfig = None):
        """Initialize ComfyServer with configuration.

        Args:
            config: Optional ComfyConfig instance. If None, default config will be used.
        """
        self.config = config if config is not None else ComfyConfig()
        self.process = None
        self.is_ready = False
        self.is_executing = False

    def _build_command(
        self,
    ) -> list[str]:
        """Build the command to start the ComfyUI server."""
        command = [
            "python",
            "main.py",
            "--disable-auto-launch",
            "--disable-metadata",
            "--listen",
        ]
        # TODO: Maybe reference comfy's cli args file here as this can quickly become a mess
        if self.config.GPU_ONLY:
            command.append("--gpu-only")
        elif self.config.HIGH_VRAM:
            command.append("--high-vram")
        elif self.config.CPU_ONLY:
            command.append("--cpu")
        return command

    def queue_prompt(self, data: QueuePromptData):
        import urllib

        serialized = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            f"http://{self.config.SERVER_HOST}:{self.config.SERVER_PORT}/prompt",
            data=serialized,
        )

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

    def start(self) -> None:
        """
        Start the ComfyUI server process.

        Raises:
            ServerStartupError: If the server process fails to start
        """
        try:
            if self.process is not None:
                logger.debug("ComfyUI server already running, skipping start")
                return

            command = self._build_command()
            self.process = subprocess.Popen(
                command,
                cwd=self.config.COMFYUI_PATH,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
        except Exception as e:
            raise ServerStartupError(
                f"Failed to start ComfyUI server: {str(e)}",
                {"command": command, "cwd": self.config.COMFYUI_PATH},
            )

        def stream_output(stream, prefix):
            for line in iter(stream.readline, ""):
                if line.strip():
                    logger.info(f"{prefix}: {line.strip()}")
            stream.close()

        threading.Thread(
            target=stream_output, args=(self.process.stdout, "COMFY-OUT"), daemon=True
        ).start()

    def wait_until_ready(self) -> bool:
        """
        Wait for server to become responsive.

        Raises:
            ServerStartupError: If the server fails to become responsive within timeout
        """
        url = f"http://{self.config.SERVER_HOST}:{self.config.SERVER_PORT}"
        deadline = time.time() + self.config.SERVER_TIMEOUT

        while time.time() < deadline:
            try:
                response = requests.head(url)
                if response.status_code == 200:
                    logger.info("ComfyUI server is reachable.")
                    self.is_ready = True
                    return True

            except requests.RequestException:
                pass

            time.sleep(self.config.SERVER_CHECK_DELAY)
        raise ServerStartupError(
            f"Server failed to start within {self.config.SERVER_TIMEOUT}s",
            {"url": url, "timeout": self.config.SERVER_TIMEOUT},
        )

    async def execute(
        self,
        data: ExecutionData,
        callbacks: ExecutionCallbacks = ExecutionCallbacks(),
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

        execution_started = False
        ws = None

        try:
            comfy_job = ComfyJobProgress(data.prompt)
            queue_start_time = get_time_ms()
            queue_response = self.queue_prompt(
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
                        or message_type not in self.MSG_TYPES_TO_PROCESS
                        or not comfy_job
                    ):
                        continue

                    if callbacks.on_ws_message:
                        callbacks.on_ws_message(message_type, message_data)

                    # Handle execution errors
                    if message_type == "execution_error":
                        if callbacks.on_error:
                            callbacks.on_error(message.get("data", {}))
                        raise Exception(
                            message.get("data", {}).get(
                                "exception_message",
                                "Unknown Exception while executing the workflow",
                            )
                        )

                    # Update job status
                    comfy_job.addStatusLog(
                        ComfyStatusLog.from_comfy_message(message_data, prompt_id)
                    )

                    # Handle execution progress
                    if message["type"] == "executing":
                        # Trigger start callback on first execution message
                        if not execution_started and callbacks.on_start:
                            callbacks.on_start({"process_id": data.process_id})
                            execution_started = True

                        if callbacks.on_progress:
                            callbacks.on_progress(
                                "progress",
                                {"progress": comfy_job.getPercentage()},
                                None,
                            )

                        # Check for completion
                        if message_data["node"] is None:
                            if callbacks.on_done:
                                callbacks.on_done({"process_id": data.process_id})
                            result_future.set_result(
                                ExecutionResult(
                                    prompt_id=prompt_id,
                                    queue_duration=comfy_queue_duration,
                                )
                            )
                            break

            # Start monitoring task and wait for result with timeout
            monitor_task = asyncio.create_task(monitor_ws())
            try:
                return await result_future
            except asyncio.TimeoutError:
                monitor_task.cancel()
                raise ExecutionError("Execution timed out")

        except Exception as e:
            if callbacks.on_error:
                callbacks.on_error({"error_message": str(e)})
            raise e

        finally:
            if ws:
                ws.close()
