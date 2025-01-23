"""
This is a modal function that downloads a list of models from huggingface and copies them to a volume.

The volume is then used as the /models directory in your ComfyUI container.
"""

from modal import Secret, App, Volume
from ..workflow import APP_NAME, VOLUME_NAME, image

app = App(f"{APP_NAME}-update-volume")
volume = Volume.from_name(VOLUME_NAME, create_if_missing=True)

models_to_download = [
    # format is (huggingface repo_id, the model filename, comfyui models subdirectory we want to save the model in)
    (
        "Comfy-Org/flux1-dev",
        "flux1-dev-fp8.safetensors",
        "checkpoints",
    ),
    (
        "comfyanonymous/flux_text_encoders",
        "t5xxl_fp8_e4m3fn.safetensors",
        "clip",
    ),
    ("comfyanonymous/flux_text_encoders", "clip_l.safetensors", "clip"),
]


@app.function(
    volumes={"/volume": volume},
    image=image,
    timeout=3600,
)
def hf_download(repo_id: str, filename: str, model_type: str):
    from huggingface_hub import hf_hub_download

    print(f"Downloading {filename} from {repo_id} to {model_type}")

    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=f"/volume/{model_type}",
    )


@app.local_entrypoint()
def update_volume():
    list(hf_download.starmap(models_to_download))
