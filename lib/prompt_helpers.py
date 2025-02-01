def assign_values_if_path_exists(workflow: dict, values_to_assign: dict) -> None:
    """
    Recursively assign values to workflow based on dot-notation paths.
    Example paths:
    - "1.inputs.value"
    - "2.class_type.params.strength"
    """

    def assign_value(obj: dict, path: list[str], value: any) -> None:
        """Recursively traverse the object and assign the value"""
        if len(path) == 1:
            obj[path[0]] = value
            return

        key = path[0]
        if key not in obj:
            raise ValueError(f"Invalid path segment '{key}' in object")

        assign_value(obj[key], path[1:], value)

    for path, value in values_to_assign.items():
        try:
            path_parts = path.split(".")
            assign_value(workflow, path_parts, value)
        except (KeyError, TypeError) as e:
            raise ValueError(f"Invalid path: {path}. Error: {str(e)}")
