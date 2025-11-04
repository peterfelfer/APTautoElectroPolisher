from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import yaml

from apt_polisher.io import find_project_root

RECIPES_DIR = Path("recipes")


class RecipeConfigError(RuntimeError):
    """Raised when a recipe file is invalid."""


@dataclass
class MotionMacro:
    name: str
    file: Optional[str] = None  # optional path to a G-code macro file
    description: Optional[str] = None


@dataclass
class PolishingCycleConfig:
    mode: str
    duration_s: Optional[float] = None
    max_cycles: Optional[int] = None
    target_charge_c: Optional[float] = None


@dataclass
class Recipe:
    name: str
    description: str
    motion_macros: Dict[str, MotionMacro]
    safe_z_mm: float
    pickup_macro: str
    place_macro: str
    contact: Dict[str, float]
    polishing_waveform: Dict[str, float]
    polishing_cycle: PolishingCycleConfig
    cleaning: Dict[str, float]
    imaging: Dict[str, float]
    default_voltage_v: float
    current_limit_a: float


def _load_yaml(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except OSError as exc:
        raise RecipeConfigError(f"Failed to read recipe file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RecipeConfigError(f"Invalid YAML in recipe file {path}: {exc}") from exc


def _require_keys(obj: dict, keys: Sequence[str], context: str) -> None:
    for key in keys:
        if key not in obj:
            raise RecipeConfigError(f"Missing required key '{key}' in {context}")


def _load_motion_macros(data: dict) -> Dict[str, MotionMacro]:
    macros_raw = data.get("motion_macros", {})
    macros: Dict[str, MotionMacro] = {}
    if not isinstance(macros_raw, dict):
        raise RecipeConfigError("motion_macros must be a mapping")
    for name, payload in macros_raw.items():
        if isinstance(payload, dict):
            macros[name] = MotionMacro(
                name=name,
                file=payload.get("file"),
                description=payload.get("description"),
            )
        elif isinstance(payload, str):
            macros[name] = MotionMacro(name=name, file=payload)
        else:
            raise RecipeConfigError(f"Invalid motion macro definition for '{name}'")
    return macros


def _load_cycle(data: dict) -> PolishingCycleConfig:
    cycle_raw = data.get("polishing", {}).get("cycle", {})
    if not isinstance(cycle_raw, dict):
        raise RecipeConfigError("polishing.cycle must be a mapping")
    mode = cycle_raw.get("mode", "time")
    if mode not in {"time", "cycles", "charge"}:
        raise RecipeConfigError(f"Unsupported polishing cycle mode '{mode}'")
    return PolishingCycleConfig(
        mode=mode,
        duration_s=cycle_raw.get("duration_s"),
        max_cycles=cycle_raw.get("max_cycles"),
        target_charge_c=cycle_raw.get("target_charge_c"),
    )


def _parse_recipe_data(name: str, data: dict) -> Recipe:
    metadata = data.get("metadata", {})
    description = metadata.get("description", f"Recipe {name}")

    motion = data.get("motion", {})
    polishing = data.get("polishing", {})
    cleaning = data.get("cleaning", {})
    imaging = data.get("imaging", {})

    _require_keys(motion, ["safe_z_mm", "pickup_macro", "place_macro"], "motion")
    _require_keys(polishing, ["waveform", "contact"], "polishing")

    macros = _load_motion_macros(data)
    cycle_cfg = _load_cycle(data)

    return Recipe(
        name=name,
        description=description,
        motion_macros=macros,
        safe_z_mm=float(motion["safe_z_mm"]),
        pickup_macro=str(motion["pickup_macro"]),
        place_macro=str(motion["place_macro"]),
        contact={k: float(v) for k, v in polishing.get("contact", {}).items()},
        polishing_waveform={k: float(v) for k, v in polishing.get("waveform", {}).items()},
        polishing_cycle=cycle_cfg,
        cleaning={k: float(v) for k, v in cleaning.items()},
        imaging={k: float(v) for k, v in imaging.items()},
        default_voltage_v=float(polishing.get("voltage_v", 8.0)),
        current_limit_a=float(polishing.get("current_limit_a", 0.6)),
    )


class RecipeLoader:
    """Loads recipe YAML files from the recipes directory."""

    def __init__(self, recipes_dir: Optional[Path] = None) -> None:
        root = find_project_root()
        self.recipes_dir = root / (recipes_dir or RECIPES_DIR)

    def list(self) -> List[str]:
        if not self.recipes_dir.exists():
            return []
        entries = []
        for path in self.recipes_dir.glob("*.yml"):
            entries.append(path.stem)
        for path in self.recipes_dir.glob("*.yaml"):
            entries.append(path.stem)
        return sorted(set(entries))

    def load(self, name: str) -> Recipe:
        candidates = [
            self.recipes_dir / f"{name}.yml",
            self.recipes_dir / f"{name}.yaml",
        ]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise RecipeConfigError(f"Recipe '{name}' not found in {self.recipes_dir}")
        data = _load_yaml(path)
        return _parse_recipe_data(name, data)


def list_recipes() -> List[str]:
    return RecipeLoader().list()


def load_recipe(name: str) -> Recipe:
    return RecipeLoader().load(name)
