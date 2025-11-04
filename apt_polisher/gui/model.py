"""Data models shared between the GUI and backend orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING, Tuple


class MachineStatus(Enum):
    """High-level machine state."""

    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    WAITING_INPUT = auto()
    WAITING_OUTPUT = auto()
    ERROR = auto()


class BufferType(Enum):
    """Enumerates available specimen buffers."""

    INPUT = "input"
    OUTPUT = "output"


@dataclass(slots=True)
class BufferSlot:
    """Represents a single specimen slot reported by an inductive sensor."""

    index: int
    occupied: bool = False
    specimen_id: Optional[str] = None
    in_process: bool = False


@dataclass(slots=True)
class BufferStatus:
    """Collection of buffer slots of a given type."""

    buffer_type: BufferType
    slots: List[BufferSlot] = field(default_factory=list)

    def occupied_slots(self) -> int:
        return sum(1 for slot in self.slots if slot.occupied)

    def capacity(self) -> int:
        return len(self.slots)

    def first_available(self) -> Optional[BufferSlot]:
        for slot in self.slots:
            if not slot.occupied:
                return slot
        return None

    def first_occupied(self) -> Optional[BufferSlot]:
        for slot in self.slots:
            if slot.occupied and not slot.in_process:
                return slot
        return None


@dataclass(slots=True)
class CameraFrame:
    """One captured frame, optionally with an analysed overlay."""

    image_path: Path
    analysis_path: Optional[Path] = None
    label: Optional[str] = None
    timestamp: Optional[float] = None


if TYPE_CHECKING:  # pragma: no cover - for type hinting only
    from apt_polisher.telemetry import TelemetrySeries


@dataclass(slots=True)
class MachineSnapshot:
    """Aggregated state for presentation."""

    status: MachineStatus
    active_gcode: Optional[str] = None
    last_completed_specimen: Optional[str] = None
    buffers: Dict[BufferType, BufferStatus] = field(default_factory=dict)
    camera_feeds: Dict[str, List[CameraFrame]] = field(default_factory=dict)
    current_reading_ma: Optional[float] = None
    message: Optional[str] = None
    telemetry: Optional["TelemetrySeries"] = None
    gantry_position: Optional[Tuple[float, float, float]] = None
