import json
import os
import shutil
import subprocess
import time
from zipfile import ZipFile

import requests


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


def clone_repository(repo_url, commit_hash, target_path):
    print("cloning repo", repo_url, commit_hash, target_path)
    if not os.path.exists(target_path):
        os.makedirs(target_path)

    api_url = f"{repo_url}/archive/{commit_hash}.zip"

    headers = {
        "Authorization": f"token {os.environ.get('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github.v3+json",
    }

    response = requests.get(api_url, headers=headers)
    response.raise_for_status()

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


def clone_custom_nodes(custom_nodes, comfyui_path):
    for repo_url, repo_data in custom_nodes.items():
        if not repo_data["disabled"]:
            with_token = repo_url.replace(
                "https://", f"https://{os.environ.get('GITHUB_TOKEN')}@"
            )

            if "recursive" in repo_data and repo_data["recursive"]:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--recursive",
                        repo_url,
                        os.path.join(
                            comfyui_path,
                            "custom_nodes",
                            repo_url.rstrip("/").split("/")[-1],
                        ),
                    ]
                )
            else:
                clone_repository(
                    with_token,
                    repo_data["hash"],
                    os.path.join(comfyui_path, "custom_nodes", repo_url.split("/")[-1]),
                )


def start_server():
    print("Installing comfy dependencies.")

    # Start an instance of comfy to make sure all deps are installed.
    command = [
        "python",
        "main.py",
        "--disable-auto-launch",
        "--disable-metadata",
        "--cpu",
    ]
    server_process = subprocess.Popen(command, cwd="/root/ComfyUI")
    return server_process


def check_server(server_process):
    url = "http://127.0.0.1:8188"
    retries = 600
    delay = 2000
    for _ in range(retries):
        if server_process.poll() is not None:
            print("Subprocess has ended")
            break

        try:
            response = requests.head(url)
            if response.status_code == 200:
                print("API is reachable")
            return True

        except requests.RequestException:
            pass

        time.sleep(delay / 1000)

    print(f"Failed to connect to server at {url} after {retries} attempts.")
    return False


def download_comfy(snapshot_path: str, enable_private_repos: bool = False):
    path = os.path.join("/root", snapshot_path)
    # Check if private repos are enabled and github token is set
    if enable_private_repos and not os.environ.get("GITHUB_TOKEN", None):
        raise ValueError(
            "GITHUB_TOKEN is not set, but private repos are enabled. Please create a github secret in modal and pass it to this function in the image build phase."
        )

    with open(path, "r") as file:
        json_data = file.read()

    data = json.loads(json_data)

    comfyui_repo_url = "https://github.com/comfyanonymous/ComfyUI"
    comfyui_path = "/root/ComfyUI"
    comfy_commit_hash = data["comfyui"]

    clone_repository(comfyui_repo_url, comfy_commit_hash, comfyui_path)

    clone_custom_nodes(data["git_custom_nodes"], comfyui_path)
    # download_musepose_models()
    server = start_server()
    check_server(server)
    server.terminate()
    print("Finished installing dependencies.")
