# Preload Models with Snapshotting - SDXL Workflow

This example demonstrates how to preload custom nodes to CPU memory and use modal's memory snapshotting to cut down on the cold start times.

You can also preload diffusion models to CPU memory. This is helpful when the container has slow disk reads and you want to speed up the inference times.

It uses the `experimental_server.py` file to override the ComfyUI server to run in the main thread.

## How to run locally

- Move the files to the root of the repo, under `src/`.
- Fix the imports in `workflow.py` so that they point to the correct files.
- Run `modal run src.update_volume` to update the volume with the needed models.
- Run `modal serve src.workflow` to serve the app locally.
