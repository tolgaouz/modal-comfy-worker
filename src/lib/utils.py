import time
from typing import Dict, Any, TypeVar

T = TypeVar("T", bound=Dict[str, Any])


def deep_merge(dict1: T, dict2: T) -> T:
    """
    Recursively merge two dictionaries.

    Args:
        dict1: The primary dictionary whose values take precedence
        dict2: The secondary dictionary to merge into

    Returns:
        A new dictionary containing merged key-value pairs

    Example:
        >>> d1 = {'a': 1, 'b': {'x': 2}}
        >>> d2 = {'a': 0, 'b': {'y': 3}}
        >>> deep_merge(d1, d2)
        {'a': 1, 'b': {'x': 2, 'y': 3}}
    """
    result = dict2.copy()

    for key, value in dict1.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(value, result[key])
        else:
            result[key] = value

    return result


def get_time_ms() -> int:
    return int(round(time.time() * 1000))
