from collections.abc import Mapping
from pathlib import Path
from typing import Any

def unpath_dict(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, Mapping):
        return obj.__class__(
            (unpath_dict(k), unpath_dict(v))
            for k, v in obj.items()
        )

    if isinstance(obj, list):
        return [unpath_dict(x) for x in obj]

    if isinstance(obj, tuple):
        return tuple(unpath_dict(x) for x in obj)

    if isinstance(obj, set):
        return {unpath_dict(x) for x in obj}

    return obj
