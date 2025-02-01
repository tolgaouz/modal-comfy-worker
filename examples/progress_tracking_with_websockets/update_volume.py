from modal import Image, App, Volume

image = (
    Image.debian_slim()
    .pip_install("huggingface_hub[hf_transfer]==0.26.2")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = App("comfy-flux-ws-update-volume")
volume = Volume.from_name("comfy-flux-ws-volume")

models_to_download = [
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
