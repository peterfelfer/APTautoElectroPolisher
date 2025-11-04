"""Abstractions for current-sensing hardware."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class CurrentReading:
    """Container for a single current measurement."""

    timestamp: float
    amperes: float


class CurrentSensor(Protocol):
    """Interface for current sensors that can provide instantaneous readings."""

    def read(self) -> CurrentReading:
        """Return the most recent current reading."""
        raise NotImplementedError


class DummyCurrentSensor:
    """Placeholder implementation that always returns zero current."""

    def read(self) -> CurrentReading:
        return CurrentReading(timestamp=time.time(), amperes=0.0)
