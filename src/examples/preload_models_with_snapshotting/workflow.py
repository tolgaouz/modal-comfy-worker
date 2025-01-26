from modal import Secret, enter, App, Volume, method, exception, functions, asgi_app
from ...comfy.experimental_server import ExperimentalComfyServer
from ...lib.image import get_comfy_image
from ...comfy.models import ExecutionCallbacks, ExecutionData
from ...lib.logger import logger
from ...lib.utils import get_time_ms
from .prompt_constructor import WorkflowInput, construct_workflow_prompt
import os
from fastapi import FastAPI, HTTPException

local_snapshot_path = os.path.join(os.path.dirname(__file__), "snapshot.json")
local_prompt_path = os.path.join(os.path.dirname(__file__), "prompt.json")

github_secret = Secret.from_name("github-secret")

image = get_comfy_image(
    local_snapshot_path=local_snapshot_path,
    local_prompt_path=local_prompt_path,
    github_secret=github_secret,
)

APP_NAME = "comfy-preload-models-sdxl"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)
volume = Volume.from_name(VOLUME_NAME, create_if_missing=True)


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
    enable_memory_snapshot=True,
)
class ComfyWorkflow:
    @enter(snap=True)
    def run_this_on_container_startup(self):
        self.web_app = FastAPI()
        self.server = ExperimentalComfyServer(
            preload_models=[
                "/root/ComfyUI/models/checkpoints/sd_xl_refiner_1.0.safetensors",
                "/root/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors",
            ]
        )

    @method()
    async def infer(self, payload: WorkflowInput):
        server_ws_connection = None
        job_start_time = get_time_ms()
        prompt = construct_workflow_prompt(payload)

        try:
            # Define callbacks for execution monitoring
            callbacks = ExecutionCallbacks(
                on_error=lambda error_data: (logger.error(error_data),),
                on_done=lambda msg: (
                    logger.info("Job Completed. Sending Completion Event."),
                ),
                on_ws_message=lambda type, msg: (
                    logger.info(f"Received message: {type} - {msg}"),
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

            return execution_result
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
        call = await ComfyWorkflow().infer.spawn(payload)
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
