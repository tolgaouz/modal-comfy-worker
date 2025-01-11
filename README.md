# Comfy Modal Worker

This repository is aimed to be a template for creating Modal workers for running ComfyUI workflows. It will be extended with new features and improvements over time. Currently it supports:

- WebSocket communication with the server (Optional, will return via REST API when completed if not enabled)
- Volume updaters for using custom models (see the `volume_updaters` folder for examples)
- Installing custom nodes from private repos
- Progress reporting back to the server and calculating the percentage of completion
- Using a snapshot to install custom nodes and specifying the ComfyUI version

The worker is designed to be modular and easy to extend. It currently uses a single Modal app for all the functionality.

## Table of Contents

- [Development](#development)
- [Deployment](#deployment)
- [Using Volumes](#using-volumes)
- [Installing Custom Nodes](#installing-custom-nodes)
- [WebSocket Communication](#websocket-communication)

## Development

To run the worker locally:
`modal serve workflow`
This command will spin up a live development server synced with the remote Modal instance.

## Deployment

If you're using modal with a multi environment set up, make sure you set the correct environment:
`modal config set-environment {env_name}`.
Then deploy the worker:
`modal deploy workflow`

## Using Volumes

Volumes in Modal are used to load models into the ComfyUI instance inside workers. Workers may share volumes with other workers or have their own volumes.

I have included example volume updaters in the `volume_updaters` folder. These are used to download models from huggingface and copy them to a volume so that ComfyUI can use them. You may also want to download the models directly into the image but this is not recommended because it will increase the size of the image and slow down the startup time of the worker.

## Installing Custom Nodes

This worker supports installing custom nodes from private repos. You can specify the repos in the `snapshot.json` file. Snapshot structure follows the [Comfy Custom Node](https://github.com/ltdrdata/ComfyUI-Manager) manager snapshot format.  The `comfy/download_comfy.py` script will install the nodes from the `requirements.txt` file in each repo.

Even if you don't use any custom nodes, you should include the `snapshot.json` file in the root of the repo because it installs the ComfyUI version using the commit hash.

To be able to install private repos, you need to set the `GITHUB_TOKEN` environment variable in the Modal app. You can do this by creating a new secret in the Modal environment either through the dashboard or by running `modal secret create github_token`. Private repos are enabled by default. You can disable them by changing the line in `workflow.py`:

```python
# Enable private repos
.run_function(download_comfy, args=[snapshot_path, True], secrets=[github_secret])
# Use public repos only
# .run_function(download_comfy, args=[snapshot_path, False])
```

## WebSocket Communication

The `process_job` function in `comfy/comfy_utils.py` handles the main workflow and communicates progress via WebSockets. Here's what it sends:

- Job Started:

  ```json
  {
    "type": "job_started",
    "data": {
      "process_id": string,
      "client_id": string,
      "provider_metadata": { /* Information about the modal worker */ },
      "server_connection_time": number,
      "execution_delay_time": number
    }
  }
  ```

- Job Progress:

  ```json
  {
    "type": "job_progress",
    "data": {
      // ... All fields in the job_started message
      "percentage": number
    }
  }
  ```

- Job Completed:

  ```json
  {
    "type": "job_completed",
    "data": {
      // ... All fields in the job_started message
    }
  }
  ```

- Job Failed:

  ```json
  {
    "type": "job_failed",
    "data": {
      // ... All fields in the job_started message
      "error_message": string
    }
  }
  ```

## Using Private GitHub Repositories

If you need to use private GitHub repositories in your snapshot, you'll need to:

1. Create a GitHub Personal Access Token (Classic):
   - Go to GitHub Settings -> Developer Settings -> Personal Access Tokens -> Tokens (classic)
   - Click "Generate new token (classic)"
   - Give it a name and select the `repo` scope
   - Copy the generated token

2. Set the `GITHUB_TOKEN` environment variable:
   
   ```bash
   # In your shell
   export GITHUB_TOKEN=your_token_here
   
   # Or in Modal
   modal secret create github-token GITHUB_TOKEN=your_token_here
   ```

   Then in your Modal app:
   ```python
   from modal import Secret
   
   github_secret = Secret.from_name("github-token")
   
   @stub.function(secrets=[github_secret])
   def my_function():
       # Your code here
   ```

If you try to access a private repository without setting up the token, you'll get an error message with instructions.

For more details on creating GitHub tokens, see the [official documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.