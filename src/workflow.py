from fastapi import HTTPException
from modal import Secret, enter, App, web_endpoint, Volume
from .comfy.download_comfy import download_comfy
from .comfy.server import ComfyServer
from .lib.base_image import base_image
from pydantic import BaseModel
from .lib.logger import logger
from typing import Optional

snapshot_path = "./snapshot.json"

github_secret = Secret.from_name("github-secret")

image = base_image.copy_local_file(
    snapshot_path,
    "/root/snapshot.json",
).run_function(download_comfy, args=[snapshot_path], secrets=[github_secret])

APP_NAME = "comfy-worker"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)
volume = Volume.from_name(VOLUME_NAME)


class Input(BaseModel):
    prompt: dict  # Prompt is workflow.json with the values changed
    client_id: str  # client_id is a unique identifier for a user.
    job_id: str  # A job id is a unique identifier for a job that is used to track the job's progress and results.
    ws_connection_url: Optional[str] = ""


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
    def infer(self, data: Input):
        pass
