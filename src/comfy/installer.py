import os
import json
from typing import Dict, Any
from .config import ComfyConfig
from .download_comfy import clone_repository, clone_custom_nodes
from ..lib.logger import logger


class InstallationError(Exception):
    """Raised when installation fails"""

    pass


class ComfyInstaller:
    """Handles installation of ComfyUI and its dependencies."""

    def __init__(self, config: ComfyConfig):
        self.config = config

    def _load_snapshot(self, snapshot_path: str) -> Dict[str, Any]:
        """Load and validate snapshot configuration."""
        try:
            with open(snapshot_path) as f:
                snapshot = json.load(f)

            required_keys = ["comfyui"]
            missing_keys = [key for key in required_keys if key not in snapshot]
            if missing_keys:
                raise InstallationError(
                    f"Missing required keys in snapshot: {missing_keys}"
                )

            return snapshot
        except json.JSONDecodeError:
            raise InstallationError(f"Invalid JSON in snapshot file: {snapshot_path}")
        except FileNotFoundError:
            raise InstallationError(f"Snapshot file not found: {snapshot_path}")

    def _validate_environment(self, enable_private_repos: bool) -> None:
        """Validate environment configuration."""
        if enable_private_repos and not os.environ.get("GITHUB_TOKEN"):
            raise InstallationError(
                "GITHUB_TOKEN environment variable is required for private repositories"
            )

    def _install_comfyui(self, commit_hash: str) -> None:
        """Install core ComfyUI."""
        try:
            clone_repository(
                self.config.COMFYUI_REPO, commit_hash, self.config.COMFYUI_PATH
            )
        except Exception as e:
            raise InstallationError(f"Failed to install ComfyUI: {str(e)}")

    def _verify_installation(self) -> None:
        """Verify the installation was successful."""
        required_paths = [
            self.config.COMFYUI_PATH,
            os.path.join(self.config.COMFYUI_PATH, "main.py"),
        ]

        for path in required_paths:
            if not os.path.exists(path):
                raise InstallationError(f"Required path not found: {path}")

    def install(self, snapshot_path: str) -> None:
        """
        Install ComfyUI and custom nodes from snapshot.

        Args:
            snapshot_path: Path to the snapshot configuration file

        Raises:
            InstallationError: If installation fails
        """
        logger.info(f"Starting ComfyUI installation from {snapshot_path}")

        snapshot = self._load_snapshot(snapshot_path)

        # Install core ComfyUI
        self._install_comfyui(snapshot["comfyui"])

        # Install custom nodes
        if snapshot.get("git_custom_nodes"):
            clone_custom_nodes(snapshot["git_custom_nodes"], self.config.COMFYUI_PATH)

        # Verify installation
        self._verify_installation()

        logger.info("ComfyUI installation completed successfully")
