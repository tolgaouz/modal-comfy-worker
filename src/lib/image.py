from modal import Image, Secret
from typing import Optional

from ..comfy.download_comfy import download_comfy

base_image = (
    Image.debian_slim(python_version="3.12")
    .apt_install("git", "wget")
    .pip_install(
        "websocket-client",
        "pydantic",
        "cupy-cuda12x",
        "requests",
        "huggingface_hub[hf_transfer]==0.26.2",
    )
    .apt_install(
        "libopengl0", "libcairo2-dev", "libjpeg-dev", "libgif-dev", "pkg-config"
    )
    .pip_install(
        [
            "torch==2.5.1",
            "torchvision",
            "torchaudio",
            "xformers==0.0.28.post3",  # Updated version
            "triton==3.1.0",
        ],  # Updated version
        index_url="https://download.pytorch.org/whl/cu124",
    )
    .env(
        {
            "LD_LIBRARY_PATH": "/usr/local/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib",
            "SAFETENSORS_FAST_GPU": "1",
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
        }
    )
)


def get_comfy_image(
    local_snapshot_path: str,
    local_prompt_path: str,
    github_secret: Optional[Secret] = None,
) -> Image:
    """
    Prepares a container image with ComfyUI setup and standardized file paths.

    This function copies the snapshot.json and prompt.json files from local paths into
    the container at standardized locations (/root/snapshot.json and /root/prompt.json).
    Using standardized paths ensures consistent access across the application.

    Args:
        local_snapshot_path: Path to the local snapshot.json file
        local_prompt_path: Path to the local prompt.json file
        github_secret: Optional GitHub secret for private repository access

    Returns:
        Image: Configured Modal container image with ComfyUI setup
    """
    return (
        base_image.add_local_file(local_snapshot_path, "/root/snapshot.json", copy=True)
        .run_function(
            download_comfy, args=["/root/snapshot.json"], secrets=[github_secret]
        )
        .run_commands(["rm -rf /root/ComfyUI/models"])
        .add_local_file(local_prompt_path, "/root/prompt.json", copy=True)
    )
