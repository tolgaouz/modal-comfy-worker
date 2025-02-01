import json
import os
import shutil
import subprocess
from zipfile import ZipFile
from typing import Dict
from ..lib.logger import logger
import requests
from .server import ComfyServer
from .config import ComfyConfig


def move_all_contents(source_dir, destination_dir):
    if not os.path.exists(source_dir):
        print(f"Source directory '{source_dir}' does not exist.")
        return

    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)

    for item in os.listdir(source_dir):
        source_item = os.path.join(source_dir, item)
        destination_item = os.path.join(destination_dir, item)

        shutil.move(source_item, destination_item)
        print(f"Moved: {source_item} to {destination_item}")


def clone_repository(
    repo_url: str,
    commit_hash: str,
    target_path: str,
) -> None:
    """
    Clone a specific commit from a GitHub repository and extract it to a target path.

    Args:
        repo_url: The GitHub repository URL
        commit_hash: The specific commit hash to clone
        target_path: Local path to extract the repository to

    Raises:
        requests.RequestException: If the repository cannot be downloaded
        zipfile.BadZipFile: If the downloaded archive is corrupted
        ValueError: If trying to access a private repo without GITHUB_TOKEN
    """
    print("cloning repo", repo_url, commit_hash, target_path)
    if not os.path.exists(target_path):
        os.makedirs(target_path)

    api_url = f"{repo_url}/archive/{commit_hash}.zip"
    token = os.environ.get("GITHUB_TOKEN")

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        if e.response and e.response.status_code == 404:
            raise ValueError(
                "You are trying to clone a private GitHub repository. Make sure you have a valid "
                "GITHUB_TOKEN in your environment variables. For instructions on creating a token, "
                "visit: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens"
            )
        raise

    repo_name = repo_url.rstrip("/").split("/")[-1]
    zip_file_path = os.path.join(target_path, f"{repo_name}.zip")
    with open(zip_file_path, "wb") as file:
        file.write(response.content)

    with ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(target_path)

    move_all_contents(
        os.path.join(target_path, f"{repo_name}-{commit_hash}"), target_path
    )

    os.rmdir(os.path.join(target_path, f"{repo_name}-{commit_hash}"))
    os.remove(zip_file_path)

    requirements_file = os.path.join(target_path, "requirements.txt")
    if os.path.exists(requirements_file):
        subprocess.run(["pip", "install", "-r", requirements_file])

    print(
        f"Repository '{repo_name}' at commit '{commit_hash}' has been downloaded and extracted to {target_path}"
    )


def clone_custom_nodes(custom_nodes: Dict[str, Dict], comfyui_path: str) -> None:
    """Install custom ComfyUI nodes from their repositories."""
    for repo_url, repo_data in custom_nodes.items():
        try:
            if repo_data.get("disabled", False):
                logger.info(f"Skipping disabled node: {repo_url}")
                continue

            logger.info(f"Installing custom node from: {repo_url}")
            with_token = _add_github_token_to_url(repo_url)

            if repo_data.get("recursive", False):
                _clone_recursive_repo(with_token, comfyui_path)
            else:
                clone_repository(
                    with_token,
                    repo_data["hash"],
                    os.path.join(comfyui_path, "custom_nodes", repo_url.split("/")[-1]),
                )

        except Exception as e:
            logger.error(f"Failed to install custom node {repo_url}: {str(e)}")
            if repo_data.get("required", False):
                raise


def download_comfy(snapshot_path: str):
    with open(snapshot_path, "r") as file:
        json_data = file.read()

    data = json.loads(json_data)
    config = ComfyConfig()
    config.CPU_ONLY = True

    comfyui_repo_url = config.COMFYUI_REPO
    comfyui_path = config.COMFYUI_PATH
    comfy_commit_hash = data["comfyui"]

    clone_repository(comfyui_repo_url, comfy_commit_hash, comfyui_path)
    if data["git_custom_nodes"] and len(data["git_custom_nodes"]) > 0:
        clone_custom_nodes(data["git_custom_nodes"], comfyui_path)

    # Use ComfyServer instead of direct server management
    server = ComfyServer(config)

    logger.info("Starting ComfyUI server to install dependencies")

    server.start()

    try:
        server.wait_until_ready()
    finally:
        if server.process:
            server.process.terminate()
            logger.info("ComfyUI server terminated")

    logger.info("Finished installing dependencies")


def _add_github_token_to_url(repo_url: str) -> str:
    """Add GitHub token to repository URL if available."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return repo_url.replace("https://", f"https://{token}@")
    return repo_url


def _clone_recursive_repo(repo_url: str, comfyui_path: str) -> None:
    """Clone a repository recursively."""
    target_path = os.path.join(
        comfyui_path, "custom_nodes", repo_url.rstrip("/").split("/")[-1]
    )
    subprocess.run(["git", "clone", "--recursive", repo_url, target_path], check=True)
