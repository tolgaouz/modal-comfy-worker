"""
This module is a modified version of the ComfyUI server.
It executes comfy workflows in the main thread by overriding some parts of Comfy
and using a global executor. This is experimental and may not work for all workflows.

It allows:
- Loading models to GPU during Modal snapshotting for instant cold starts
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
                if self.on_send_sync:
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


class GPUModelCache:
    """Manages pre-loaded GPU models for instant access"""

    def __init__(self):
        self.gpu_models = {}  # Store actual GPU models
        self.model_patchers = {}  # Store ModelPatcher instances
        self.clip_models = {}  # Store CLIP models
        self.vae_models = {}  # Store VAE models

    def add_model(self, model_key: str, model_patcher, clip=None, vae=None):
        """Add a pre-loaded model to the cache"""
        self.model_patchers[model_key] = model_patcher
        if clip:
            self.clip_models[model_key] = clip
        if vae:
            self.vae_models[model_key] = vae
        logger.info(f"Cached GPU model: {model_key}")

    def get_model(self, model_key: str):
        """Get a pre-loaded model from cache"""
        return self.model_patchers.get(model_key)

    def get_clip(self, model_key: str):
        """Get a pre-loaded CLIP model from cache"""
        return self.clip_models.get(model_key)

    def get_vae(self, model_key: str):
        """Get a pre-loaded VAE model from cache"""
        return self.vae_models.get(model_key)


class ExperimentalComfyServer:
    """Experimental ComfyUI server that runs workflows in the main thread.

    Features:
    - Executes workflows without starting separate server process
    - Preloads models to GPU memory for instant cold starts via Modal snapshotting
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

    def __init__(
        self, config=None, preload_models: List[str] = [], snapshot_mode: bool = False
    ):
        """Initialize experimental server.

        Args:
            config: Compatibility with regular server (not used)
            preload_models: List of model paths to preload
            snapshot_mode: Whether we're in Modal snapshot creation mode
        """
        logger.info("Initializing experimental server")
        self.preload_models = preload_models
        self.snapshot_mode = snapshot_mode
        self.initialized = False
        self.gpu_cache = GPUModelCache()
        self.executor = None
        self.original_functions = {}  # Store original functions for restoration

        # Set up ComfyUI environment
        self._setup_comfy_environment()

        if snapshot_mode:
            # During snapshot creation, load models to GPU
            self._preload_models_to_gpu(preload_models)
        else:
            # During execution, override model loading to use GPU cache
            self._override_model_loading()

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

    async def execute(
        self, data: ExecutionData, callbacks: ExecutionCallbacks = ExecutionCallbacks()
    ):
        import execution
        import torch

        """Execute a workflow directly in the main thread using GPU-cached models."""

        if not self.initialized:
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
                execution.validate_prompt(data.prompt)
            )
            validate_time = time.time() - start_time
            logger.info(f"Validation took {validate_time:.2f} seconds")

            if not is_valid:
                raise Exception(error)

            # Execute workflow with pre-loaded GPU models
            with torch.inference_mode():
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

    def model_load_override_with_gpu(self):
        """Initialize GPU-related components and override model loading"""
        if not self.initialized:
            self.initialized = True

    def _setup_comfy_environment(self):
        """Set up ComfyUI environment and initialize components"""
        import sys

        sys.stdout.reconfigure(line_buffering=True)
        sys.path.append("/root/ComfyUI")

        import nodes

        # Initialize executor and components
        self.executor = CustomPromptExecutor()
        start_time = time.time() * 1000
        nodes.init_extra_nodes()
        init_time = time.time() * 1000 - start_time
        logger.info(f"Node initialization took {init_time:.2f} ms")

    def _preload_models_to_gpu(self, model_paths: List[str]):
        """Load models directly to GPU during snapshot creation"""
        import torch
        import comfy.sd
        import comfy.model_management

        logger.info("Preloading models to GPU memory for snapshotting...")

        for model_path in model_paths:
            full_path = os.path.join("/volume/", model_path)
            model_key = os.path.basename(model_path)

            logger.info(f"Loading {model_path} to GPU...")
            start_time = time.time()

            try:
                # Load model directly to GPU
                with torch.cuda.device(0):  # Ensure we're using GPU 0
                    model_patcher, clip, vae, _ = comfy.sd.load_checkpoint_guess_config(
                        full_path,
                        output_vae=True,
                        output_clip=True,
                        model_options={
                            "dtype": torch.float16
                        },  # Use FP16 for memory efficiency
                    )

                    # Force load to GPU immediately
                    comfy.model_management.load_models_gpu(
                        [model_patcher], force_full_load=True
                    )

                    # Cache the loaded models
                    self.gpu_cache.add_model(model_key, model_patcher, clip, vae)

                    load_time = time.time() - start_time
                    file_size = os.path.getsize(full_path) / (1024 * 1024 * 1024)  # GB
                    logger.info(
                        f"Model loaded to GPU in {load_time:.2f}s ({file_size:.2f} GB)"
                    )

            except Exception as e:
                logger.error(f"Failed to load {model_path} to GPU: {str(e)}")

        logger.info("GPU model preloading complete")

    def _override_model_loading(self):
        """Override ComfyUI's model loading to use GPU-cached models"""
        import comfy.sd
        import comfy.model_management
        import nodes

        # Store original functions
        self.original_functions["load_checkpoint_guess_config"] = (
            comfy.sd.load_checkpoint_guess_config
        )
        self.original_functions["load_models_gpu"] = (
            comfy.model_management.load_models_gpu
        )

        # Override checkpoint loading
        def cached_load_checkpoint_guess_config(ckpt_path, **kwargs):
            model_key = os.path.basename(ckpt_path)

            # Check if we have this model in GPU cache
            cached_model = self.gpu_cache.get_model(model_key)
            cached_clip = self.gpu_cache.get_clip(model_key)
            cached_vae = self.gpu_cache.get_vae(model_key)

            if cached_model:
                logger.info(f"Using GPU-cached model: {model_key}")
                return (cached_model, cached_clip, cached_vae, None)

            # Fallback to original loading
            logger.info(f"Model not in cache, loading from disk: {model_key}")
            return self.original_functions["load_checkpoint_guess_config"](
                ckpt_path, **kwargs
            )

        # Override GPU loading to skip for cached models
        def cached_load_models_gpu(models, **kwargs):
            models_to_load = []
            for model in models:
                # Check if this model is already in our GPU cache
                model_id = getattr(model, "model_id", None)
                if model_id and model_id in self.gpu_cache.model_patchers:
                    logger.info(f"Skipping GPU load for cached model: {model_id}")
                    continue
                models_to_load.append(model)

            if models_to_load:
                return self.original_functions["load_models_gpu"](
                    models_to_load, **kwargs
                )

        # Apply overrides
        comfy.sd.load_checkpoint_guess_config = cached_load_checkpoint_guess_config
        comfy.model_management.load_models_gpu = cached_load_models_gpu

        # Override the CheckpointLoaderSimple node to use our cache
        original_checkpoint_loader = nodes.CheckpointLoaderSimple.load_checkpoint

        def cached_checkpoint_load(self, ckpt_name):
            model_key = ckpt_name

            # Check GPU cache first
            cached_model = self.gpu_cache.get_model(model_key)
            cached_clip = self.gpu_cache.get_clip(model_key)
            cached_vae = self.gpu_cache.get_vae(model_key)

            if cached_model:
                logger.info(f"Using GPU-cached checkpoint: {model_key}")
                return (cached_model, cached_clip, cached_vae)

            # Fallback to original
            return original_checkpoint_loader(self, ckpt_name)

        nodes.CheckpointLoaderSimple.load_checkpoint = cached_checkpoint_load

        logger.info("Model loading overrides applied")

    def _restore_original_functions(self):
        """Restore original ComfyUI functions (cleanup)"""
        import comfy.sd
        import comfy.model_management

        if "load_checkpoint_guess_config" in self.original_functions:
            comfy.sd.load_checkpoint_guess_config = self.original_functions[
                "load_checkpoint_guess_config"
            ]
        if "load_models_gpu" in self.original_functions:
            comfy.model_management.load_models_gpu = self.original_functions[
                "load_models_gpu"
            ]

    def __del__(self):
        """Cleanup when server is destroyed"""
        self._restore_original_functions()
