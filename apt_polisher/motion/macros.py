"""Utilities for executing motion macros (G-code snippets)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, Optional

from apt_polisher.io import find_project_root
from apt_polisher.recipes import MotionMacro, RECIPES_DIR


class MacroExecutionError(RuntimeError):
    """Raised when a macro cannot be executed."""


class MacroRunner:
    """Loads and executes G-code macros using a FluidNC client."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        root = find_project_root()
        self.base_dir = root / (base_dir or RECIPES_DIR)

    def _macro_path(self, macro: MotionMacro) -> Path:
        if not macro.file:
            raise MacroExecutionError(f"Macro '{macro.name}' does not specify a file path.")
        path = self.base_dir / macro.file
        if not path.exists():
            raise MacroExecutionError(f"Macro file not found: {path}")
        return path

    def load_lines(self, macro: MotionMacro) -> Iterator[str]:
        path = self._macro_path(macro)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("("):
                        continue
                    yield stripped
        except OSError as exc:
            raise MacroExecutionError(f"Failed to read macro '{macro.name}': {exc}") from exc

    def execute(self, client, macro: MotionMacro, wait_ok: bool = True) -> None:
        """Stream a macro into the FluidNC planner."""
        try:
            lines = list(self.load_lines(macro))
        except MacroExecutionError:
            raise
        except Exception as exc:
            raise MacroExecutionError(f"Unexpected error loading macro '{macro.name}': {exc}") from exc

        if not lines:
            return

        try:
            client.stream_gcode(lines, max_outstanding=12)
            if wait_ok and hasattr(client, "wait_until_idle"):
                client.wait_until_idle()
        except Exception as exc:
            raise MacroExecutionError(f"Failed to execute macro '{macro.name}': {exc}") from exc
