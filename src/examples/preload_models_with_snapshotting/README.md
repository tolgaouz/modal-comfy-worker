# Preload Models with Snapshotting - SDXL Workflow

This example demonstrates how to preload models to CPU memory and use modal's memory snapshotting to cut down on the cold start times.
It uses the `experimental_server.py` file to override the ComfyUI server to run in the main thread.
For now, this implementation uses a custom @app.cls decorator to set up router and inference methods until i figure out how to do it with the existing architecture.

## How to run locally

- Move the files to the root of the repo, under `src/`.
- Fix the imports in `workflow.py` so that they point to the correct files.
- Run `modal run src.update_volume` to update the volume with the needed models.
- Run `modal serve src.workflow` to serve the app locally.
