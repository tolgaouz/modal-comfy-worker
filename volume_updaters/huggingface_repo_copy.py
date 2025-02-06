import os
from huggingface_hub import snapshot_download
from lib.base_volume_updater import VolumeUpdater


class HfRepoVolumeUpdater(VolumeUpdater):
    """
    This is a volume updater that downloads a snapshot of a huggingface repo and copies it to a volume.

    Useful when you have a huggingface repo shaped exactly like ComfyUI's /models directory.
    """

    def __init__(self, hf_repo_id: str):
        super().__init__(hf_repo_id)

    async def update_volume(self):
        snapshot_download(
            repo_id=self.hf_repo_id,
            local_dir="/volume",
            cache_dir="/volume/.hf_cache",
            token=os.environ["HF_TOKEN"],
        )
