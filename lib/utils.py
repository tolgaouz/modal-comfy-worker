import time


def deep_merge(dict1, dict2):
    """
    Recursively merge two dictionaries.
    Values from dict1 take precedence over values from dict2.
    """
    result = dict2.copy()

    for key, value in dict1.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(value, result[key])
        else:
            result[key] = value

    return result


def get_time_ms():
    return int(round(time.time() * 1000))
