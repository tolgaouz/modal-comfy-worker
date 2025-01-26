# Basic SDXL Workflow

This is a basic example of how to run a SDXL workflow.

## How to run locally

- Move the files to the root of the repo, under `src/`.
- Fix the imports in `workflow.py` so that they point to the correct files.
- Run `modal run src.update_volume` to update the volume with the needed models.
- Run `modal serve src.workflow` to serve the app locally.
