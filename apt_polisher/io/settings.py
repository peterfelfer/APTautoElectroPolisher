import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

import yaml

PROJECT_MARKERS: Iterable[str] = (".git", "pyproject.toml", "config")
DEFAULT_SETTINGS_PATH = Path("config/settings.yml")
DEFAULT_POLISHING_PATH = Path("config/polishing.yml")

PathLike = Union[str, os.PathLike]


def find_project_root(markers: Iterable[str] = PROJECT_MARKERS) -> Path:
    """Attempt to locate the repository root by walking up until a marker file/dir appears."""
    start = Path(__file__).resolve().parent
    for candidate in [start] + list(start.parents):
        for marker in markers:
            if (candidate / marker).exists():
                return candidate
    return start


def _resolve(path: PathLike, project_root: Path) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = project_root / target
    return target


def _load_yaml(target: Path) -> Dict[str, Any]:
    if not target.exists():
        raise FileNotFoundError(f"settings file not found: {target}")
    with open(target, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(path: Optional[PathLike] = None) -> Dict[str, Any]:
    """Load the YAML settings file, defaulting to ``config/settings.yml`` under the project root."""
    project_root = find_project_root()
    target = _resolve(path or DEFAULT_SETTINGS_PATH, project_root)
    return _load_yaml(target)


def load_polishing_settings(path: Optional[PathLike] = None) -> Dict[str, Any]:
    """Load electropolishing process parameters from ``config/polishing.yml``."""
    project_root = find_project_root()
    target = _resolve(path or DEFAULT_POLISHING_PATH, project_root)
    return _load_yaml(target)


def update_settings_value(identifier: str, value: Any, path: Optional[PathLike] = None) -> None:
    """Update a value inside ``settings.yml`` given a dotted/indexed identifier.

    Identifiers use dot-separated keys and zero-based list indices in brackets, e.g.
    ``buffers.input_slots[0].position``.
    """

    project_root = find_project_root()
    target = _resolve(path or DEFAULT_SETTINGS_PATH, project_root)
    data = _load_yaml(target)

    def _parse_segment(segment: str) -> tuple[str, Optional[int]]:
        if "[" in segment and segment.endswith("]"):
            key, index_str = segment[:-1].split("[", 1)
            return key, int(index_str)
        return segment, None

    parts = identifier.split(".") if identifier else []
    if not parts:
        raise ValueError("Identifier must not be empty")

    cursor = data
    for segment in parts[:-1]:
        key, index = _parse_segment(segment)
        if key not in cursor:
            raise KeyError(f"Missing key '{key}' in settings for segment '{segment}'")
        cursor = cursor[key]
        if index is not None:
            if not isinstance(cursor, list):
                raise TypeError(f"Expected list at '{key}' but found {type(cursor).__name__}")
            if index >= len(cursor):
                raise IndexError(f"Index {index} out of range for '{key}'")
            cursor = cursor[index]

    last_key, last_index = _parse_segment(parts[-1])
    if last_index is not None:
        if last_key not in cursor:
            raise KeyError(f"Missing key '{last_key}' in settings for final segment")
        target_list = cursor[last_key]
        if not isinstance(target_list, list):
            raise TypeError(f"Expected list at '{last_key}' but found {type(target_list).__name__}")
        if last_index >= len(target_list):
            raise IndexError(f"Index {last_index} out of range for '{last_key}'")
        target_list[last_index] = value
    else:
        cursor[last_key] = value

    with open(target, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)
