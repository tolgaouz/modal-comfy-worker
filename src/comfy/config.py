from pydantic import BaseModel


class ComfyConfig(BaseModel):
    """Configuration settings for ComfyUI installation and setup."""

    COMFYUI_REPO: str = "https://github.com/comfyanonymous/ComfyUI"
    COMFYUI_PATH: str = "/root/ComfyUI"
    SERVER_PORT: int = 8188
    SERVER_HOST: str = "127.0.0.1"
    SERVER_TIMEOUT: int = 600
    SERVER_CHECK_DELAY: float = 2.0

    GPU_ONLY: bool = False
    HIGH_VRAM: bool = False
    CPU_ONLY: bool = False

    class Config:
        env_prefix = "COMFY_"
        frozen = True  # Makes the config immutable
