from modal import Secret, enter, App, web_endpoint, Volume
from .comfy.download_comfy import download_comfy
from .comfy.server import ComfyServer
from .lib.base_image import base_image
from .comfy.models import ExecutionData
import os

# This is the path to the snapshot.json file that will be used to launch the ComfyUI server.
local_snapshot_path = os.path.join(os.path.dirname(__file__), "snapshot.example.json")
target_snapshot_path = "./snapshot.json"

github_secret = Secret.from_name("github-secret")

image = base_image.copy_local_file(
    local_snapshot_path,
    target_snapshot_path,
).run_function(download_comfy, args=[target_snapshot_path], secrets=[github_secret])

APP_NAME = "comfy-worker"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)
volume = Volume.from_name(VOLUME_NAME)


@app.cls(
    image=image,
    # Add in your secrets
    secrets=[],
    # Add in your volumes
    volumes={"/volume": volume},
    gpu="T4",
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
    async def infer(self, data: ExecutionData):
        # Execute the prompt
        execution_result = await self.server.execute(data=data)
        return execution_result


"""
The following is the modal function that launches the ComfyUI server as an interactive web server.
You can use this to debug your workflows or send them to people.
@app.function(
    allow_concurrent_inputs=10,
    concurrency_limit=1,
    secrets=[aws_secret, upstash_secret],
    image=image,
    volumes={"/volume": volume},
    container_idle_timeout=30,
    timeout=1800,
    gpu="H100",
    cpu=1,
    memory=10240,
)
@web_server(8000, startup_timeout=60)
def ui():
    launch_comfy(8000, gpu_only=False, wait_for_ready=False)
"""
