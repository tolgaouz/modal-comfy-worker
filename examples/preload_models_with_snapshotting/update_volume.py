from modal import App, Volume
from .workflow import image, APP_NAME, VOLUME_NAME

app = App(f"{APP_NAME}-update-volume")
volume = Volume.from_name(VOLUME_NAME, create_if_missing=True)

models_to_download = [
    (
        "stabilityai/stable-diffusion-xl-base-1.0",
        "sd_xl_base_1.0.safetensors",
        "checkpoints",
    ),
    (
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        "sd_xl_refiner_1.0.safetensors",
        "checkpoints",
    ),
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
