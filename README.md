# Modal ComfyUI API Worker

This repository provides a template for deploying ComfyUI workflows as robust and scalable APIs using [Modal](https://modal.com/). It offers an opinionated yet flexible structure to streamline the process of turning your ComfyUI workflows into production-ready services.

## What is this for?

This repository is designed to help developers easily deploy ComfyUI workflows as APIs on Modal. It provides a pre-configured structure and boilerplate code to handle common tasks, allowing you to focus on your specific workflows. Key functionalities include:

- **Running ComfyUI Server:** Launches a ComfyUI server as a subprocess within a Modal worker.
- **Workflow Management:** Provides utilities for queueing prompts, checking job status, and canceling jobs.
- **API Routing:** Implements standard API endpoints within `workflow.py` for:
  - **Synchronous and Asynchronous Inference:** Run workflows and get results synchronously or asynchronously.
  - **Status Checks:** Query the status of running or completed jobs.
  - **Job Cancellation:** Cancel queued or running jobs.
- **Custom Node Management:** Utilizes `snapshot.json` to load custom ComfyUI nodes, supporting private repositories when `GITHUB_TOKEN` is available.
- **Dynamic Prompt Construction:** Employs `prompt.json` and `prompt_constructor.py` to dynamically generate ComfyUI prompts based on API requests, mapping API inputs to ComfyUI node inputs.
- **Efficient Model Loading:** Leverages `volume_updaters` to download models directly to Modal volumes, avoiding the need to include large models in the Docker image and reducing image size.

## Key Features

- **Opinionated Structure:** Provides a well-defined project structure that promotes maintainability and scalability for your Modal ComfyUI applications. This structure is designed to be a starting point, and you are expected to adapt and modify the provided files to match the specific needs of your ComfyUI workflows.
- **Ready-to-use ComfyUI Boilerplate:** Includes pre-built logic for launching the ComfyUI server, queueing prompts, and handling events, allowing you to focus on your workflows. The `src/comfy` folder contains the core logic for running ComfyUI as a subprocess, managing prompts, and handling callbacks.
- **Standard API Routing:** The `workflow.py` file includes a standard way to manage API endpoints for inference, status checks, and job management. This is not provided by default by Modal and adds significant value for building production APIs.
- **Dynamic Prompt Generation:** Easily map API request parameters to ComfyUI workflow inputs using `prompt.json` and `prompt_constructor.py`, making your APIs flexible and user-friendly. The `prompt_constructor.py` file is where you'll implement the logic to transform API requests into ComfyUI prompts.
- **Interactive UI Server:** Alongside the API endpoints, you can also access the standard ComfyUI web interface, allowing for visual workflow editing, manual prompting, and real-time feedback.
- **Optimized Model Management:** `volume_updaters` ensure efficient model loading and reduce Docker image size by downloading models to volumes on demand. This allows you to manage large model files separately from your application code.
- **Customizable and Extensible:** The repository is designed to be a starting point. You are expected to adapt and modify the provided files (especially `workflow.py` and `prompt_constructor.py`) to match the specific needs of your ComfyUI workflows. The example implementations in the `examples` folder serve as further guidance.

## Getting Started

### **Clone the repository:**

  ```bash
  git clone <repository-url>
  cd <repository-name>
  ```

### **Install dependencies:**

  ```bash
  pip install -r requirements.txt
  ```

### **Configure your Modal app:**

- Ensure you have a Modal account and the Modal CLI installed and configured.
- Modify the files in this repository, especially `workflow.py` and `prompt_constructor.py`, to match your ComfyUI workflow and API requirements.
- Add your ComfyUI workflow (exported via the API mode) to the `prompt.json` file.
- Adjust `snapshot.json` to include any custom ComfyUI nodes you need.

### **Deploy your Modal app:**

  ```bash
  modal deploy src.workflow
  ```

### **Access your API endpoints:**

- After deployment, Modal will provide you with URLs for your API endpoints.
- **API Endpoints:** Use these endpoints to interact with your ComfyUI workflows programmatically, as described in the "Understanding the Routing" section below.

### **Interactive UI**

- To enable the interactive UI, you must uncomment the lines in `src/workflow.py` that calls the `ui` function.
- Modal will provide a separate URL for accessing the ComfyUI interactive user interface. Open this URL in your web browser to access the standard ComfyUI UI. This allows you to:
  - Visually design and modify workflows.
  - Manually queue prompts and monitor their progress.
  - Test workflows and experiment with different parameters directly through the UI.
  - Get real-time previews of generated images and other outputs.

### Understanding the Routing

The `workflow.py` file implements a standard routing mechanism for managing API requests related to ComfyUI workflows.

Here's a breakdown of the routing concept:

- **Endpoint Definitions:** The `workflow.py` file defines standard endpoints for interacting with workflows:
  - `/infer`: For synchronous inference requests (blocking until completion).
  - `/infer_async`: For asynchronous inference requests (non-blocking, returns job ID).
  - `/check_status/{job_id}`: To check the status of an asynchronous job.
  - `/cancel/{job_id}`: To cancel a running or queued job.

- **Centralized Request Handling:** The routing logic within `workflow.py` centralizes the handling of different types of API requests, making it easier to manage and extend your API.

- **Abstraction over Modal Functions:** It provides an abstraction layer over direct Modal function calls, offering a more structured and user-friendly API interface.

- **Example Usage (Conceptual):**

  **Synchronous Inference:**

  ```bash
  curl -X POST <your-modal-app-url>/infer \
      -H "Content-Type: application/json" \
      -d '{"prompt_params": {"node_1": {"input_text": "A beautiful landscape"}}}'
  ```

  **Asynchronous Inference:**

  ```bash
  curl -X POST <your-modal-app-url>/infer_async \
      -H "Content-Type: application/json" \
      -d '{"prompt_params": {"node_1": {"input_text": "A futuristic city"}}}'
  ```

  This will return a `job_id`.

  **Check Status:**

  ```bash
  curl <your-modal-app-url>/check_status/{job_id}
  ```

  **Cancel Job:**

  ```bash
  curl <your-modal-app-url>/cancel/{job_id}
  ```

By using this routing convention, you can build a well-organized and easily accessible API for your ComfyUI workflows deployed on Modal.

## Experimental Features

This repository also includes an experimental feature that allows you to run ComfyUI workflows directly in the main thread, potentially reducing inference times and improving error handling.

### Main Thread Execution

The `src/comfy/experimental_server.py` file provides an alternative to the standard ComfyUI server. This experimental server:

- **Runs ComfyUI in the main thread:** This eliminates the overhead of inter-process communication, potentially speeding up inference.
- **Provides clearer error handling:** Errors are raised directly in the main thread, making debugging easier.
- **Preloads models to CPU:** It can preload models into CPU memory, leveraging Modal's memory snapshotting feature to reduce cold start times.

### Usage

To use the experimental server, you'll need to:

1. Modify your `workflow.py` to use `ExperimentalComfyServer` instead of `ComfyServer`.
2. Configure the `preload_models` parameter in the `ExperimentalComfyServer` constructor to specify which models to load into CPU memory.
3. Ensure that your Modal app is configured to use memory snapshotting.

### Example

The `src/examples/preload_models_with_snapshotting` folder contains an example implementation that demonstrates how to use the experimental server with model preloading and memory snapshotting. This example can serve as a practical guide for integrating this feature into your own workflows.

**Note:** This feature is experimental and may not be suitable for all workflows. It is recommended to test it thoroughly before using it in production.

## Customization

Remember that this repository is a starting point. You will likely need to customize the files to fit your specific ComfyUI workflows and API requirements.

- **`src/workflow.py`:** This file serves as the entry point for the Modal app. It defines the API routes, the ComfyUI server, and the main logic for your application.
- **`src/prompt_constructor.py`:** Implement the logic to construct ComfyUI prompts dynamically based on API request parameters.
- **`prompt.json`:** Your ComfyUI workflow (exported via the API mode).
- **`snapshot.json`:** Add or modify entries in this file to include the custom ComfyUI nodes required by your workflows.
- **`src/comfy/server.py`, `src/comfy/models.py`, `src/lib/*`:** These files provide the underlying boilerplate and utility functions. You may need to adjust them in advanced use cases, but for most workflows, customization will primarily focus on `workflow.py`, `prompt_constructor.py`, `prompt.json`, and `snapshot.json`.

## Examples

The `src/examples` folder contains example implementations to further illustrate how to use this repository. These examples demonstrate specific features and can serve as a practical guide for building your own Modal ComfyUI APIs.

## Contributing

Contributions are welcome! If you have suggestions, bug reports, or feature requests, please open an issue or submit a pull request.

## License

This project is open-sourced under the MIT License - see the [LICENSE](LICENSE) file for details.

## TODO

- [ ] Add a way to run the ComfyUI interactive server with ComfyUI-Mananager properly working.
- [ ] Add streaming output examples
- [ ] Add model file caching to the container start-up functions to use Modal's snapshot caching.
