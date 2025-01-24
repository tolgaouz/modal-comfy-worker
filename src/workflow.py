from modal import Secret, App, Volume, asgi_app
from .lib.image import get_comfy_image
import os
from .lib.router import ModalRouter
from .prompt_constructor import WorkflowInput

# This is the path to the snapshot.json file that will be used to launch the ComfyUI server.
local_snapshot_path = os.path.join(os.path.dirname(__file__), "snapshot.json")

github_secret = Secret.from_name("github-secret")

image = get_comfy_image(local_snapshot_path, github_secret)

APP_NAME = "comfy-worker"
VOLUME_NAME = f"{APP_NAME}-volume"

app = App(APP_NAME)
volume = Volume.from_name(VOLUME_NAME, create_if_missing=True)


# Your processing function
async def process_job(payload: WorkflowInput):
    try:
        return {"result": f"Generated image for: {payload.prompt}"}
    except Exception as e:
        raise Exception(f"Error processing job: {e}")


# Create the router with the payload type
router = ModalRouter(
    app=app,
    image=image,
    volumes={"/root/ComfyUI/models": volume},
    run_job_function=process_job,
    payload_type=WorkflowInput,
)


@app.function(
    image=image,
    volumes={"/root/ComfyUI/models": volume},
)
@asgi_app()
def comfy_worker():
    return router.asgi_app()


"""
The following is the modal function that launches the ComfyUI server as an interactive web server.
You can use this to debug your workflows or send them to people.
@app.function(
    allow_concurrent_inputs=10,
    concurrency_limit=1,
    image=image,
    volumes={"/root/ComfyUI/models": volume},
    container_idle_timeout=30,
    timeout=1800,
    gpu="l4",
    cpu=1,
    memory=10240,
)
@web_server(8188, startup_timeout=120)
def ui():
    config = ComfyConfig(SERVER_HOST="0.0.0.0", SERVER_PORT=8188)
    server = ComfyServer(config=config)
    server.start()
"""
