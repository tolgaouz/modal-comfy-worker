import subprocess
import time
import logging
import requests
import threading
from .config import ComfyConfig
from ..lib.exceptions import ServerStartupError

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
        """
        Start the ComfyUI server process.

        Raises:
            ServerStartupError: If the server process fails to start
        """
        try:
            command = self._build_command(cpu_only)
            self.process = subprocess.Popen(
                command,
                cwd=self.config.COMFYUI_PATH,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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

        threading.Thread(
            target=stream_output, args=(self.process.stderr, "COMFY-ERR"), daemon=True
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
                requests.head(url).raise_for_status()
                logger.info("ComfyUI server is ready")
                return True
            except requests.RequestException:
                # Check if process has terminated
                if self.process and self.process.poll() is not None:
                    stderr = (
                        self.process.stderr.read()
                        if self.process.stderr
                        else "No error output"
                    )
                    raise ServerStartupError(
                        "Server process terminated unexpectedly",
                        {"stderr": stderr, "return_code": self.process.returncode},
                    )
                time.sleep(self.config.SERVER_CHECK_DELAY)

        raise ServerStartupError(
            f"Server failed to start within {self.config.SERVER_TIMEOUT}s",
            {"url": url, "timeout": self.config.SERVER_TIMEOUT},
        )
