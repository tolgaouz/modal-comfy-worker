import json
import copy
from pydantic import BaseModel
from ...lib.prompt_helpers import assign_values_if_path_exists


class WorkflowInput(BaseModel):
    prompt: str


def construct_workflow_prompt(input: WorkflowInput) -> dict:
    """
    Generate a keyframe prompt based on the provided settings.
    """
    # Read the workflow JSON file fresh for each call
    with open("/root/prompt.json", "r") as file:
        source_workflow = json.load(file)

    # Clone the workflow to avoid mutating the original object
    workflow = copy.deepcopy(source_workflow)

    # Define values to assign
    values_to_assign = {"6.inputs.text": input.prompt}

    # Assign all values to the workflow
    assign_values_if_path_exists(workflow, values_to_assign)

    return workflow
