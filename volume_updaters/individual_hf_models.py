"""
This is a function that downloads a list of models from huggingface and copies them to a volume.

The volume is then used as the /models directory in your ComfyUI container.
"""

import asyncio
from lib.base_volume_updater import VolumeUpdater


class HfModelsVolumeUpdater(VolumeUpdater):
    def __init__(self, models_to_download):
        self.models_to_download = models_to_download

    async def update_volume(self):
        async def download_model(repo_id: str, filename: str, model_type: str):
            from huggingface_hub import hf_hub_download

            print(f"Downloading {filename} from {repo_id} to {model_type}")

            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=f"/volume/{model_type}",
            )

        await asyncio.gather(
            *[download_model(*model) for model in self.models_to_download]
        )
