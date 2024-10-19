from fastapi import HTTPException
from modal import Secret, enter, App, web_endpoint, gpu, Volume
from .comfy.comfy_utils import launch_comfy, process_job
from .comfy.download_comfy import download_comfy
from .base_image import base_image
from pydantic import BaseModel
from .utils.logger import logger
from typing import Optional

snapshot_path = "./snapshot.json"

github_secret = Secret.from_name("github-secret")

image = (
    base_image.copy_local_file(
        snapshot_path,
        "/root/snapshot.json",
    )
    # Enable private repos
    .run_function(download_comfy, args=[snapshot_path, True], secrets=[github_secret])
    # Use public repos only
    # .run_function(download_comfy, args=[snapshot_path, False])
    .copy_local_file(
        "./src/keyframe/extra_model_paths.yaml",
        "/root/ComfyUI/extra_model_paths.yaml",
    )
)

APP_NAME = "comfy-worker"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)
volume = Volume.from_name(VOLUME_NAME)


class Input(BaseModel):
    prompt: dict
    client_id: str
    job_id: str
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
        launch_comfy()

    @web_endpoint(method="POST")
    def run(self, data: Input):
        try:
            completion_data = process_job(data)
            if "error_message" in completion_data:
                raise HTTPException(status_code=500, detail=completion_data)
            return completion_data
        except Exception as e:
            logger.error(str(e))
            return {
                "client_id": data.client_id,
                "job_id": data.job_id,
                "error_message": str(e),
            }
