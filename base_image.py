from modal import Image

base_image = (
    Image.debian_slim(python_version="3.12")
    .apt_install("git", "wget")
    .pip_install("git+https://github.com/modal-labs/asgiproxy.git", "httpx", "tqdm")
    .pip_install("cupy-cuda12x")
    .pip_install(
        "websocket-client",
        "pydantic==1.10.11",
    )
    .apt_install(
        "libopengl0", "libcairo2-dev", "libjpeg-dev", "libgif-dev", "pkg-config"
    )
    .run_commands(
        "pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu124",
    )
)
