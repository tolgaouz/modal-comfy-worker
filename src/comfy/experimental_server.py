"""
This module is a modified version of the ComfyUI server.
It executes comfy workflows in the main thread by overriding some parts of Comfy
and using a global executor. This is experimental and may not work for all workflows.

It allows:
- Loading models to the CPU and leverage modal's snapshotting feature to reduce cold start times.
- Running workflows in the main thread without initializing the comfyui server routes and queue.

Limitations:
- Since we don't initialize the comfyui server routes and queue, we don't have access to the UI or the queue.
So make sure you set allow_concurrent_inputs to 1 in your modal app.
"""

import time
from .models import ExecutionData, ExecutionCallbacks
from ..lib.utils import check_disk_speed
from typing import Dict, List, Optional, Callable
import os
import asyncio
from ..lib.logger import logger


class DummyServer:
    """
    Overrides the ComfyUI server to be able to run in the main thread.
    """

    def __new__(cls):
        import server
        import execution

        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)

        class Server(server.PromptServer):
            def __init__(self, loop, on_send_sync=None):
                super().__init__(loop)
                server.PromptServer.instance = self
                q = execution.PromptQueue(server.PromptServer.instance)
                self.client_id = "dummy"
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


class ExperimentalComfyServer:
    """Experimental ComfyUI server that runs workflows in the main thread.

    Features:
    - Executes workflows without starting separate server process
    - Allows model preloading to CPU for faster cold starts
    - Uses modified ComfyUI components for direct execution
    - Maintains similar interface to regular ComfyServer
    """

    MSG_TYPES_TO_PROCESS = [
        "executing",
        "execution_cached",
        "execution_complete",
        "execution_start",
        "progress",
        "status",
        "completed",
    ]

    def __init__(self, config=None, preload_models: List[str] = []):
        """Initialize experimental server.

        Args:
            config: Compatibility with regular server (not used)
            preload_models: List of model paths to preload to CPU
        """
        logger.info("Initializing experimental server")
        self.preload_models = preload_models
        self.initialized = False
        self.model_cache = {}
        self.executor = None

        # Set up ComfyUI environment overrides
        self._override_comfy(preload_models)

        read_speed, write_speed = check_disk_speed()
        logger.info(
            f"Disk speeds - Read: {read_speed:.2f} MB/s, Write: {write_speed:.2f} MB/s"
        )

    def start(self):
        """Compatibility method - initialization happens in constructor"""
        pass

    def wait_until_ready(self):
        """No-op for experimental server since everything runs in-process"""
        return True

    def model_load_override_with_gpu(self):
        """Initialize GPU-related components and override model loading"""
        if not self.initialized:
            # Import ComfyUI components after CUDA setup
            import comfy.utils

            # Patch model loading and logging
            self._patch_model_loading(comfy.utils)

            self.initialized = True

    async def execute(
        self, data: ExecutionData, callbacks: ExecutionCallbacks = ExecutionCallbacks()
    ):
        import execution
        import torch

        """Execute a workflow directly in the main thread.

        Args:
            data: Execution data containing prompt and process ID
            callbacks: Callbacks for execution events

        Returns:
            Execution result dictionary

        Raises:
            Exception: If execution fails
        """
        # Initialize GPU components if needed
        self.model_load_override_with_gpu()

        result_future = asyncio.Future()
        result_data = {"process_id": data.process_id}

        try:
            # Set up execution callbacks
            def on_error(error_data: Dict):
                callbacks.on_error and callbacks.on_error(error_data)
                result_future.set_exception(Exception(str(error_data)))

            def on_done(msg: Dict):
                callbacks.on_done and callbacks.on_done(msg)
                result_future.set_result(result_data)

            def on_ws_message(event_type: str, msg: dict, sid=None):
                if event_type in self.MSG_TYPES_TO_PROCESS and callbacks.on_ws_message:
                    callbacks.on_ws_message(event_type, msg)

            # Configure executor callbacks
            self.executor.on_error = on_error
            self.executor.on_done = on_done
            self.executor.server.on_send_sync = on_ws_message

            start_time = time.time()
            is_valid, error, outputs_to_execute, node_errors = (
                execution.validate_prompt(
                    data.prompt,
                )
            )
            validate_time = time.time() - start_time
            logger.info(f"Validation took {validate_time:.2f} seconds")

            if not is_valid:
                raise Exception(error)

            # Execute workflow with CUDA optimizations
            with torch.inference_mode(), torch.autocast(
                device_type="cuda", enabled=False
            ):
                self.executor.execute(
                    prompt=data.prompt,
                    prompt_id=data.process_id,
                    extra_data={"client_id": data.process_id},
                    execute_outputs=outputs_to_execute,
                )

            return await result_future

        except Exception as e:
            result_future.set_exception(e)
            raise

    def _patch_model_loading(self, comfy_utils):
        """Override ComfyUI's model loading to use CPU cache"""
        original_load = comfy_utils.load_torch_file

        def cached_load(path, *args, **kwargs):
            filename = os.path.basename(path)
            for model_key, state_dict in self.model_cache.items():
                if filename in str(model_key):
                    logger.info(f"Using cached model {model_key}")
                    return state_dict
            return original_load(path, *args, **kwargs)

        comfy_utils.load_torch_file = cached_load

    def _override_comfy(self, preload_models: List[str] = []):
        import sys

        # Force immediate flush for streaming logs
        sys.stdout.reconfigure(line_buffering=True)

        """Initialize ComfyUI environment"""
        import sys

        sys.path.append("/root/ComfyUI")

        import nodes

        # Initialize executor and components
        self.executor = CustomPromptExecutor()
        start_time = time.time() * 1000
        nodes.init_extra_nodes()
        init_time = time.time() * 1000 - start_time
        logger.info(f"Node initialization took {init_time:.2f} ms")

        # Initialize custom nodes
        self._preload_models_to_cpu(preload_models)

    def _setup_folder_paths(self):
        """
        TODO: This method will be used to mimic extra_model_paths functionality in ComfyUI.
        """
        import folder_paths

        pass

    def _preload_models_to_cpu(self, model_paths: List[str] = []):
        """Preload models into CPU memory with disk speed monitoring"""
        import safetensors.torch
        import time

        logger.info("Preloading models to CPU memory...")
        for model_path in model_paths:
            full_path = os.path.join("/volume/", model_path)
            logger.info(f"Loading {model_path} into CPU memory...")

            start_time = time.time()
            try:
                # Load state dict to CPU
                if model_path.endswith(".safetensors"):
                    state_dict = safetensors.torch.load_file(full_path, device="cpu")

                load_time = time.time() - start_time
                file_size = os.path.getsize(full_path) / (
                    1024 * 1024 * 1024
                )  # Size in GB
                loading_speed = file_size / load_time

                logger.info(
                    f"Model loaded in {load_time:.2f}s ({loading_speed:.2f} GB/s)"
                )
                self.model_cache[model_path.split("/")[-1]] = state_dict
                logger.info(f"Successfully cached {model_path} in CPU memory")

            except Exception as e:
                logger.error(f"Failed to load {model_path}: {str(e)}")

        logger.info("Preloaded models to CPU memory")
