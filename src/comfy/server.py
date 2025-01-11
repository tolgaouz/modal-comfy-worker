import subprocess
import time
import logging
import requests
import threading
from .config import ComfyConfig

logger = logging.getLogger(__name__)


class ComfyServer:
    """Manages ComfyUI server lifecycle."""

    def __init__(self, config: ComfyConfig):
        self.config = config
        self.process = None

    def _build_command(self, cpu_only: bool = False) -> list[str]:
        """Build the command to start the ComfyUI server."""
        command = [
            "python",
            "main.py",
            "--disable-auto-launch",
            "--disable-metadata",
        ]
        if cpu_only:
            command.append("--cpu")
        return command

    def start(self, cpu_only: bool = False) -> None:
        """Start the ComfyUI server process."""
        command = self._build_command(cpu_only)
        self.process = subprocess.Popen(
            command,
            cwd=self.config.COMFYUI_PATH,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        # Start threads to handle stdout and stderr streams

        def stream_output(stream, prefix):
            """Helper function to stream output from process to stdout"""
            for line in iter(stream.readline, ""):
                if line.strip():  # Only print non-empty lines
                    if prefix == "COMFY-ERR":
                        logger.error(f"{prefix}: {line.strip()}")
                    else:
                        logger.info(f"{prefix}: {line.strip()}")
            stream.close()

        stdout_thread = threading.Thread(
            target=stream_output, args=(self.process.stdout, "COMFY-OUT"), daemon=True
        )

        stdout_thread.start()

    def wait_until_ready(self) -> bool:
        """Wait for server to become responsive."""
        url = f"http://{self.config.SERVER_HOST}:{self.config.SERVER_PORT}"
        deadline = time.time() + self.config.SERVER_TIMEOUT

        while time.time() < deadline:
            try:
                requests.head(url).raise_for_status()
                logger.info("ComfyUI server is ready")
                return True
            except requests.RequestException:
                time.sleep(self.config.SERVER_CHECK_DELAY)

        raise TimeoutError(
            f"Server failed to start within {self.config.SERVER_TIMEOUT}s"
        )
