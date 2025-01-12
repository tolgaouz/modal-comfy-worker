from modal import Image

base_image = (
    Image.debian_slim(python_version="3.12")
    .apt_install("git", "wget")
    .pip_install("websocket-client", "pydantic==1.10.11", "cupy-cuda12x", "requests")
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
        }
    )
)
