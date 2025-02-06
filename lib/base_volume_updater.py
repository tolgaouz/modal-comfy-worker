from abc import ABC, abstractmethod


class VolumeUpdater(ABC):
    @abstractmethod
    def __init__(self, models_to_download):
        pass

    @abstractmethod
    async def update_volume(self):
        """
        This method should be implemented by subclasses to update the volume.
        Volume will be mounted at /volume in the container.
        """
        pass
