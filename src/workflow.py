from modal import Secret, enter, App, web_endpoint, Volume
from .comfy.server import ComfyServer
from .lib.image import get_comfy_image
from .comfy.models import ExecutionData
import os
import logging

# Setup logger for better debugging and monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# This is the path to the snapshot.json file that will be used to launch the ComfyUI server.
local_snapshot_path = os.path.join(os.path.dirname(__file__), "snapshot.example.json")

# Ensure that the file exists before proceeding
if not os.path.exists(local_snapshot_path):
    logger.error(f"Snapshot file not found at {local_snapshot_path}")
    raise FileNotFoundError(f"Snapshot file not found: {local_snapshot_path}")

github_secret = Secret.from_name("github-secret")

# Validate the image retrieval process
try:
    image = get_comfy_image(local_snapshot_path, github_secret)
except Exception as e:
    logger.error(f"Error while getting Comfy image: {str(e)}")
    raise

APP_NAME = "comfy-worker"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)

# Ensure volume exists before using it
try:
    volume = Volume.from_name(VOLUME_NAME)
except Exception as e:
    logger.error(f"Error while retrieving volume {VOLUME_NAME}: {str(e)}")
    raise

@app.cls(
    image=image,
    secrets=[github_secret],  # Added secret handling here
    volumes={"/root/ComfyUI/models": volume},
    gpu="T4",
    container_idle_timeout=60 * 2,
    retries=3,
)
class ComfyWorkflow:
    @enter()
    def run_this_on_container_startup(self):
        """Initialize and start the server, with error handling."""
        try:
            self.server = ComfyServer()
            self.server.start()
            self.server.wait_until_ready()
            logger.info("ComfyServer started and ready.")
        except Exception as e:
            logger.error(f"Error starting ComfyServer: {str(e)}")
            raise

    @web_endpoint(method="POST")
    async def infer(self, data: ExecutionData) -> dict:
        """Handle inference request with error handling."""
        try:
            execution_result = await self.server.execute(data=data)
            return execution_result
        except Exception as e:
            logger.error(f"Error during inference: {str(e)}")
            return {"error": "Inference failed", "message": str(e)}

"""
The following is the modal function that launches the ComfyUI server as an interactive web server.
You can use this to debug your workflows or send them to people.
@app.function(
    allow_concurrent_inputs=10,
    concurrency_limit=1,
    secrets=[aws_secret, upstash_secret],
    image=image,
    volumes={"/root/ComfyUI/models": volume},
    container_idle_timeout=30,
    timeout=1800,
    gpu="H100",
    cpu=1,
    memory=10240,
)
@web_server(8000, startup_timeout=120)
def ui():
    launch_comfy(8000, gpu_only=False, wait_for_ready=False)
"""
