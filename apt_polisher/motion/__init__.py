"""Motion-control utilities for the electropolisher."""

from __future__ import annotations

from typing import Optional

from .gcode import make_sine_z_gcode, save_ngc
from .macros import MacroExecutionError, MacroRunner

_fluidnc_error: Optional[RuntimeError] = None

try:
    from .fluidnc_client import CNCStatus, FluidNCClient  # type: ignore
except RuntimeError as exc:
    CNCStatus = None  # type: ignore[assignment]
    FluidNCClient = None  # type: ignore[assignment]
    _fluidnc_error = exc

__all__ = [
    "CNCStatus",
    "FluidNCClient",
    "make_sine_z_gcode",
    "save_ngc",
    "MacroRunner",
    "MacroExecutionError",
]


def require_fluidnc_client() -> None:
    """Raise the deferred FluidNC import error, if any."""
    if _fluidnc_error is not None:
        raise _fluidnc_error
