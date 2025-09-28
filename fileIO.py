import os
from pathlib import Path
from typing import Any, Dict
import yaml

PROJECT_NAME = "autoPolisher"
SETTINGS_FILE = "settings.yml"

def find_project_root(project_name: str = PROJECT_NAME) -> Path:
    # 1) PyCharm env var (and child)
    env = os.environ.get("PYCHARM_PROJECT_DIR")
    if env:
        p = Path(env)
        if p.name == project_name and p.is_dir():
            return p.resolve()
        child = p / project_name
        if child.is_dir():
            return child.resolve()

    # 2) Walk up from this file (or CWD) looking for a folder named project_name
    start = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd().resolve()
    for parent in [start] + list(start.parents):
        if parent.name == project_name:
            return parent.resolve()
        cand = parent / project_name
        if cand.is_dir():
            return cand.resolve()

    # 3) Fallback to the common PyCharm default
    return (Path.home() / "PycharmProjects" / project_name).resolve()

def load_settings(filename: str = SETTINGS_FILE, project_name: str = PROJECT_NAME) -> Dict[str, Any]:
    project_root = find_project_root(project_name)
    path = project_root / filename
    if not path.exists():
        raise FileNotFoundError(f"settings file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data

