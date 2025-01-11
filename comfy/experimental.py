import asyncio
from typing import Optional, Callable, List
import os
from ..lib.utils import check_disk_speed
from ..lib.json_encoder import JSONEncoder
import json
import websocket
import logging
import time

logger = logging.getLogger(__name__)

initialized = False
executor = None
MODEL_CACHE = {}


# Create server
class DummyServer:
    def __new__(cls):
        import server
        import execution

        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)

        class Server(server.PromptServer):
            def __init__(self, loop, on_send_sync=None):
                super().__init__(loop)
                q = execution.PromptQueue(self.instance)
                self.client_id = "duummy"
                self.prompt_queue = q
                self.on_send_sync = on_send_sync

            def send_sync(self, event, data, sid=None):
                self.on_send_sync(event, data, sid)

        return Server(event_loop, on_send_sync=None)


class CustomPromptExecutor:
    """Defer imports until ComfyUI is on system path"""

    def __new__(cls, lru_size=None):
        # Import here after ComfyUI is in path
        import execution

        class Executor(execution.PromptExecutor):
            def __init__(self, lru_size=None):
                server = DummyServer()
                super().__init__(server, lru_size)
                self.on_start: Optional[Callable[[dict], None]] = None
                self.on_error: Optional[Callable[[dict], None]] = None
                self.on_progress: Optional[Callable[[dict], None]] = None
                self.on_cached_nodes: Optional[Callable[[dict], None]] = None
                self.on_interrupt: Optional[Callable[[dict], None]] = None
                self.on_done: Optional[Callable[[dict], None]] = None
                self.server = server

            def add_message(self, event: str, data: dict, broadcast: bool):
                print("add_msg", data)
                super().add_message(event, data, broadcast)
                try:
                    if event == "execution_start" and self.on_start:
                        self.on_start(data)
                    elif event == "execution_cached" and self.on_cached_nodes:
                        self.on_cached_nodes(data)
                    elif event == "execution_error" and self.on_error:
                        self.on_error(data)
                    elif event == "execution_interrupted" and self.on_interrupt:
                        self.on_interrupt(data)
                    elif event == "execution_success" and self.on_done:
                        self.on_done(data)
                except Exception as e:
                    print(f"Error in callback: {str(e)}")

        return Executor(lru_size)


def setup_folder_paths(comfy_path="/root/ComfyUI", models_path="/root/ComfyUI/models"):
    """
    Setup ComfyUI folder structure for reading models.
    TODO: Ideally this either needs to
    - Set up folder paths using comfy's own functionality (Preferred)
    - Set up folder paths using the extra_model_paths.yaml if its given.
    """
    import folder_paths

    # Override default paths
    folder_paths.folder_names_and_paths = {
        "checkpoints": (
            [os.path.join(models_path, "checkpoints")],
            folder_paths.supported_pt_extensions,
        ),
        "configs": ([os.path.join(models_path, "configs")], [".yaml"]),
        "loras": (
            [os.path.join(models_path, "loras"), "/characters"],
            folder_paths.supported_pt_extensions,
        ),
        "vae": (
            [os.path.join(models_path, "vae")],
            folder_paths.supported_pt_extensions,
        ),
        "vae_approx": (
            [os.path.join(models_path, "vae_approx")],
            folder_paths.supported_pt_extensions,
        ),
        "diffusion_models": (
            [os.path.join(models_path, "diffusion_models")],
            folder_paths.supported_pt_extensions,
        ),
        "clip": (
            [os.path.join(models_path, "clip")],
            folder_paths.supported_pt_extensions,
        ),
        "unet": (
            [os.path.join(models_path, "unet")],
            folder_paths.supported_pt_extensions,
        ),
        "ipadapter": (
            [os.path.join(models_path, "ipadapter")],
            folder_paths.supported_pt_extensions,
        ),
        "clip_vision": (
            [os.path.join(models_path, "clip_vision")],
            folder_paths.supported_pt_extensions,
        ),
        "embeddings": (
            [os.path.join(models_path, "embeddings")],
            folder_paths.supported_pt_extensions,
        ),
        "diffusers": ([os.path.join(models_path, "diffusers")], ["folder"]),
        "controlnet": (
            [os.path.join(models_path, "controlnet")],
            folder_paths.supported_pt_extensions,
        ),
        "upscale_models": (
            [os.path.join(models_path, "upscale_models")],
            folder_paths.supported_pt_extensions,
        ),
        "custom_nodes": ([os.path.join(comfy_path, "custom_nodes")], set()),
    }


def preload_models_to_cpu(model_paths: List[str] = []):
    """Preload models into CPU memory with disk speed monitoring"""
    import safetensors.torch
    import time

    print("Preloading models to CPU memory...")
    for model_path in model_paths:
        full_path = os.path.join("/volume/", model_path)
        print(f"Loading {model_path} into CPU memory...")

        start_time = time.time()
        try:
            # Load state dict to CPU
            if model_path.endswith(".safetensors"):
                state_dict = safetensors.torch.load_file(full_path, device="cpu")

            load_time = time.time() - start_time
            file_size = os.path.getsize(full_path) / (1024 * 1024 * 1024)  # Size in GB
            loading_speed = file_size / load_time

            print(f"Model loaded in {load_time:.2f}s ({loading_speed:.2f} GB/s)")
            global model_cache
            model_cache[model_path.split("/")[-1]] = state_dict
            print(f"Successfully cached {model_path} in CPU memory")

        except Exception as e:
            print(f"Failed to load {model_path}: {str(e)}")

    print("Preloaded models to CPU memory")


def override_comfy(preload_models: List[str] = []):
    # Configure logging immediately
    import logging
    import sys

    # Remove any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure root logger
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Force immediate flush for streaming logs
    sys.stdout.reconfigure(line_buffering=True)

    global executor
    """Initialize ComfyUI environment"""
    import sys

    sys.path.append("/root/ComfyUI")

    setup_folder_paths()

    read_speed, write_speed = check_disk_speed()
    print(f"Disk speeds - Read: {read_speed:.2f} MB/s, Write: {write_speed:.2f} MB/s")
    # Initialize custom nodes
    preload_models_to_cpu(preload_models)


# Need to run this when gpu is available
def model_load_override_with_gpu():
    global initialized
    global executor
    if not initialized:
        # Optimize CUDA settings
        # Set up cuda options after gpu is available since @enter doesnt expose gpu.
        import comfy.sd
        import comfy.utils
        import logging
        import execution
        import nodes

        nodes.init_extra_nodes()

        original_load_file = comfy.utils.load_torch_file

        def cached_load_torch_file(path, *args, **kwargs):
            """Enhanced loader that uses our CPU cache"""
            filename = os.path.basename(path)
            print(f"Looking for {filename} in cache...")

            # Check our CPU cache
            for model_key, state_dict in model_cache.items():
                if filename in str(model_key):
                    print(f"Found {filename} in CPU cache")
                    return state_dict

            print(f"Loading {filename} from disk")
            return original_load_file(path, *args, **kwargs)

        # Patch ComfyUI's model loading
        comfy.utils.load_torch_file = cached_load_torch_file

        # Monkey patch ComfyUI's logging to ensure we see its output
        def patch_logger(module):
            logger = logging.getLogger(module.__name__)
            module.logging = logger
            return logger

        # Patch main modules
        for module in [nodes, execution, comfy.sd, comfy.utils]:
            patch_logger(module)

        executor = CustomPromptExecutor()
        initialized = True


async def experimental_run_prompt(data: Input, websockets=True):
    # Setting up custom logging handler
    server_ws_connection = None
    job_start_time = get_time_ms()
    logger.info(f"Job ID: {data.process_id}. User ID: {data.client_id}")
    logger.info(f"User ID: {data.client_id}")
    logger.info(f"Settings: {json.dumps(data.settings, cls=JSONEncoder)}")

    to_send_back = {
        "email": data.email,
        "client_id": data.client_id,
        "process_id": data.process_id,
        "diffusion_type": data.diffusion_type,
        "worker_id": os.environ.get("MODAL_TASK_ID", "Unknown"),
        "provider_metadata": {
            "region": os.environ.get("MODAL_REGION", "Unknown"),
            "cloud_provider": os.environ.get("MODAL_CLOUD_PROVIDER", "Unknown"),
            "container_id": os.environ.get("MODAL_TASK_ID", "Unknown"),
        },
        "settings": data.settings,
        "execution_time": 0,
        "execution_delay_time": 0,
    }

    comfy_job = ComfyJob(data.prompt)
    start = time.time() * 1000

    try:
        if websockets:
            log_redis(
                "Starting server ws connection. Connection URL: " + data.connection_url
            )
            server_connect_start_time = get_time_ms()
            server_ws_connection = websocket.WebSocket()
            server_ws_connection.connect(data.connection_url)
            server_connection_time = get_time_ms() - server_connect_start_time
            log_redis(
                f"Connected to Server. Time to connect: {server_connection_time} ms"
            )
            to_send_back["server_connection_time"] = int(server_connection_time)

            # Send job started message
            send_ws_message(
                server_ws_connection,
                "worker:job_started",
                {
                    "type": "worker:job_started",
                    "data": {
                        "process_id": data.process_id,
                        "client_id": data.client_id,
                    },
                },
            )
    except Exception as e:
        log_redis(f"Failed to establish websocket connection to server: {e}", "error")
        log_redis(
            "Continuing job execution... Will return via REST API when completed.",
            "error",
        )
        server_ws_connection = None

    try:
        execution_data = ExecutionData(prompt=data.prompt, process_id=data.process_id)

        callbacks = ExecutionCallbacks(
            on_error=lambda error_data: (
                log_redis(error_data, "error"),
                send_ws_message(
                    server_ws_connection,
                    "worker:job_failed",
                    deep_merge(
                        to_send_back,
                        {"error_message": error_data.get("exception_message", "")},
                    ),
                ),
            ),
            on_done=lambda msg: (
                # Changed setattr to dictionary assignment
                to_send_back.update(
                    {"execution_time": int(time.time() * 1000 - start)}
                ),
                send_ws_message(
                    server_ws_connection, "worker:job_completed", to_send_back
                )
                if server_ws_connection
                else None,
                log_redis(
                    f"Job Completed for: Job ID {data.process_id}. Sending Completion Event."
                ),
            ),
            on_progress=lambda event, msg, sid: (
                print(f"Progress: {event}", msg),
                comfy_job.addStatusLog(create_status_log(msg, data.process_id)),
                send_ws_message(
                    server_ws_connection,
                    "worker:job_progress",
                    {
                        **create_timestamped_data(data.process_id, data),
                        "percentage": comfy_job.getPercentage(),
                    },
                )
                if server_ws_connection
                else None,
                log_redis(f"Job Progress: {comfy_job.getPercentage()}"),
            )
            if event in message_types_to_process
            else None,
            on_start=lambda msg: (
                # Changed setattr to dictionary assignment
                to_send_back.update(
                    {"execution_delay_time": int(time.time() * 1000 - job_start_time)}
                ),
                print(f"Execution start took: {time.time()*1000 - start}"),
            ),
        )

        await experimental_execute(data=execution_data, callbacks=callbacks, timeout=60)

        return to_send_back

    except Exception as e:
        log_redis(f"Error in execution: {str(e)}", "error")
        raise Exception(
            f"Unexpected exception while executing prompt. Please contact us on discord about the issue. Job ID: {data.process_id}"
        )
    finally:
        if server_ws_connection:
            server_ws_connection.close()


async def experimental_execute(
    data: ExecutionData, callbacks: ExecutionCallbacks, timeout: int = 60
) -> Dict:
    global executor
    import execution

    model_load_override_with_gpu()

    """
    Execute a task with configurable callbacks and return the result.

    Args:
        data: ExecutionData containing prompt and process_id
        callbacks: ExecutionCallbacks instance containing callback functions
        timeout: Maximum time to wait for execution in seconds

    Returns:
        Dict containing execution results

    Raises:
        asyncio.TimeoutError: If execution exceeds timeout
        ValueError: If prompt is invalid
    """
    result_future = asyncio.Future()
    result_data = {"process_id": data.process_id}

    try:

        def on_error(error_data: Dict):
            if callbacks.on_error:
                callbacks.on_error(error_data)
            if not result_future.done():
                result_future.set_exception(Exception(str(error_data)))

        def on_done(msg: Dict):
            if callbacks.on_done:
                callbacks.on_done(msg)
            if not result_future.done():
                result_future.set_result(result_data)

        def on_progress(event: str, msg: dict, sid=None):
            if event in message_types_to_process and callbacks.on_progress:
                callbacks.on_progress(event, msg, sid)

        def on_start(msg: Dict):
            if callbacks.on_start:
                callbacks.on_start(msg)

        # Set callback handlers
        executor.on_error = on_error
        executor.on_done = on_done
        executor.on_start = on_start
        executor.server.on_send_sync = on_progress

        # Validate prompt
        is_valid, error, outputs_to_execute, node_errors = execution.validate_prompt(
            data.prompt
        )
        if not is_valid:
            print("Invalid prompt", node_errors)
            print("Error:", error)
            raise ValueError("Invalid prompt")
        # Execute prompt
        with torch.inference_mode(), torch.autocast(device_type="cuda", enabled=False):
            executor.execute(
                prompt=data.prompt,
                prompt_id=data.process_id,
                extra_data={"client_id": data.process_id},
                execute_outputs=outputs_to_execute,
            )
            print("Done executing")

        # Wait for result or timeout
        return await asyncio.wait_for(result_future, timeout=60)

    except Exception as e:
        if not result_future.done():
            result_future.set_exception(e)
        raise
