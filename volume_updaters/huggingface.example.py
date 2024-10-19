from modal import Secret, Image, App, Volume
import os
from huggingface_hub import snapshot_download
from ..workflow import APP_NAME, VOLUME_NAME

image = Image.debian_slim().pip_install("requests", "huggingface-hub")

app = App(f"{APP_NAME}-update-volume")
volume = Volume.from_name(VOLUME_NAME)

hf_repo_id = "Huggingface/example-repo"  # Repo ID of the models to download, should be based on a huggingface repo


@app.function(
    image=image,
    timeout=3600,
    secrets=[Secret.from_name("huggingface-secret")],
    volumes={"/volume": volume},
)
def updateVolume():
    print(f"Downloading contents of {hf_repo_id} to {VOLUME_NAME}")
    snapshot_download(
        repo_id=hf_repo_id,
        local_dir="/volume",
        cache_dir="/volume/.hf_cache",
        token=os.environ["HF_TOKEN"],
    )


@app.local_entrypoint()
def main():
    updateVolume.remote()
