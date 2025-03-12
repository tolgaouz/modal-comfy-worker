from modal import (
    Secret,
    enter,
    App,
    Volume,
    method,
    exception,
    functions,
    asgi_app,
    web_server,
)
from comfy.server import ComfyServer, ComfyConfig
from comfy.models import ExecutionCallbacks, ExecutionData
from lib.image import get_comfy_image
from lib.logger import logger
from lib.utils import get_time_ms
from prompt_constructor import WorkflowInput, construct_workflow_prompt
import os
from fastapi import FastAPI, HTTPException
from volume_updaters.individual_hf_models import HfModelsVolumeUpdater

APP_NAME = "comfy-worker"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)
volume = Volume.from_name(VOLUME_NAME, create_if_missing=True)

local_snapshot_path = os.path.join(os.path.dirname(__file__), "snapshot.json")
local_prompt_path = os.path.join(os.path.dirname(__file__), "prompt.json")

github_secret = Secret.from_name(
    "github-secret",
)

try:
    github_secret.hydrate()
except Exception:
    logger.error(
        "GITHUB_TOKEN not found, using dummy value. The deployment will not be able to clone private git repositories.",
    )
    github_secret = Secret.from_dict({"NO_GITHUB_TOKEN": ""})


models_to_download = [
    # format is (huggingface repo_id, the model filename, comfyui models subdirectory we want to save the model in)
    (
        "stabilityai/stable-diffusion-xl-base-1.0",
        "sd_xl_base_1.0.safetensors",
        "checkpoints",
    ),
    (
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        "sd_xl_refiner_1.0.safetensors",
        "checkpoints",
    ),
]


async def volume_updater():
    await HfModelsVolumeUpdater(models_to_download).update_volume()


image = get_comfy_image(
    local_snapshot_path=local_snapshot_path,
    local_prompt_path=local_prompt_path,
    github_secret=github_secret,
    volume_updater=volume_updater,
    volume=volume,
)


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
    container_idle_timeout=60,
    # keep_warm=1,
    retries=1,
)
class ComfyWorkflow:
    @enter()
    def run_this_on_container_startup(self):
        self.web_app = FastAPI()
        self.server = ComfyServer()
        self.server.start()
        self.server.wait_until_ready()

    @method()
    async def infer(self, payload: WorkflowInput):
        server_ws_connection = None
        job_start_time = get_time_ms()
        prompt = construct_workflow_prompt(payload)

        try:
            # Initialize img_bytes in the outer scope
            self.img_bytes = None
            # Define callbacks for execution monitoring
            callbacks = ExecutionCallbacks(
                on_error=lambda error_data: (logger.error(error_data),),
                on_done=lambda msg: (
                    logger.info("Job Completed. Sending Completion Event."),
                ),
                # The example comfy workflow sends a binary message with the image at the last node.
                # We need to extract the image from the binary message and set it as img_bytes.
                on_ws_message=lambda type, msg: (
                    logger.info(f"Received message: {type} - {msg}")
                    if type != "binary"
                    else None,
                    setattr(self, "img_bytes", msg[8:]) if type == "binary" else None,
                ),
                on_start=lambda msg: (
                    logger.info(
                        f"Execution start took: {get_time_ms() - job_start_time} ms"
                    ),
                ),
            )

            # Execute the prompt
            execution_result = await self.server.execute(
                data=ExecutionData(prompt=prompt, process_id="123"), callbacks=callbacks
            )

            json_response = execution_result.model_dump()

            if self.img_bytes:
                import base64

                # Convert img_bytes to base64
                img_base64 = base64.b64encode(self.img_bytes).decode("utf-8")
                json_response["output_image"] = img_base64

            return json_response
        except Exception as e:
            logger.error(f"Error in execution: {str(e)}")
            raise e
        finally:
            if server_ws_connection:
                server_ws_connection.close()


web_app = FastAPI()


@web_app.post("/infer_sync")
async def infer(payload: WorkflowInput):
    try:
        execution_result = ComfyWorkflow().infer.remote(payload)
        return execution_result
    except Exception as e:
        print("Error in infer", e)
        raise HTTPException(status_code=500, detail=str(e))


@web_app.post("/infer_async")
async def infer_async(payload: WorkflowInput):
    try:
        call = ComfyWorkflow().infer.spawn(payload)
        return {"call_id": call.object_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@web_app.get("/status/{call_id}")
async def status(call_id: str):
    function_call = functions.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=5)
    except exception.OutputExpiredError:
        result = {"result": None, "status": "expired"}
    except TimeoutError:
        result = {"result": None, "status": "pending"}
    return {"result": result}


@web_app.post("/cancel/{call_id}")
async def cancel(call_id: str):
    function_call = functions.FunctionCall.from_id(call_id)
    function_call.cancel()
    return {"call_id": call_id}


@app.function(image=image)
@asgi_app()
def asgi_app():
    return web_app


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
