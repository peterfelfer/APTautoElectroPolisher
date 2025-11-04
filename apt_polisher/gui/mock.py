"""Mock data providers for the GUI."""

from __future__ import annotations

import itertools
import math
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

from apt_polisher.gui.model import (
    BufferSlot,
    BufferStatus,
    BufferType,
    CameraFrame,
    MachineSnapshot,
    MachineStatus,
)
from apt_polisher.telemetry import TelemetryLogger, TelemetryRecord, TelemetrySeries


def _build_buffer(buffer_type: BufferType, size: int, occupied: int) -> BufferStatus:
    slots = []
    for idx in range(size):
        filled = idx < occupied
        slot = BufferSlot(
            index=idx + 1,
            occupied=filled,
            specimen_id=f"S{idx+1:03d}" if filled else None,
            in_process=buffer_type is BufferType.INPUT and filled and idx == 0,
        )
        slots.append(slot)
    random.shuffle(slots)
    return BufferStatus(buffer_type=buffer_type, slots=slots)


_TELEMETRY_SERIES = TelemetrySeries(max_points=600)


def _append_telemetry(counter: int, logger: Optional[TelemetryLogger] = None) -> TelemetrySeries:
    t = time.time()
    voltage = 10.0 + math.sin(counter / 6.0)
    current = 0.45 + 0.1 * math.sin(counter / 3.0 + 0.5)
    temperature = 22.0 + 2.5 * math.sin(counter / 18.0)
    record = TelemetryRecord(timestamp=t, voltage=voltage, current=current, temperature=temperature)
    _TELEMETRY_SERIES.append(record)
    if logger is not None:
        logger.log(record)
    return _TELEMETRY_SERIES


def generate_mock_snapshot(counter: int = 0, logger: Optional[TelemetryLogger] = None) -> MachineSnapshot:
    """Create a mock snapshot for demonstration purposes."""
    status_cycle = [
        MachineStatus.IDLE,
        MachineStatus.RUNNING,
        MachineStatus.WAITING_OUTPUT,
        MachineStatus.RUNNING,
        MachineStatus.PAUSED,
    ]
    status = status_cycle[counter % len(status_cycle)]
    input_buffer = _build_buffer(BufferType.INPUT, size=6, occupied=4)
    output_buffer = _build_buffer(BufferType.OUTPUT, size=6, occupied=2)
    message = None
    if status == MachineStatus.WAITING_OUTPUT:
        message = "Output buffer full. Waiting for operator intervention."
    elif status == MachineStatus.WAITING_INPUT:
        message = "No specimens available in input buffer."

    camera_feeds: Dict[str, List[CameraFrame]] = {}
    sample_dir = Path(__file__).resolve().parent / "sample_images"
    candidates = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
    if not candidates:
        sample_path = sample_dir / "placeholder.png"
        candidates = [sample_path] if sample_path.exists() else []
    for camera_idx in range(2):
        frames: List[CameraFrame] = []
        for offset, path in zip(range(3), itertools.cycle(candidates)):
            analysis_path = path if offset % 2 == 1 else None
            frames.append(CameraFrame(image_path=path, analysis_path=analysis_path, label=f"Frame {offset+1}"))
        camera_feeds[f"Camera {camera_idx+1}"] = frames

    return MachineSnapshot(
        status=status,
        active_gcode="G21\nG90\nG1 Z-0.500 F200\n...",
        last_completed_specimen="S057",
        buffers={
            BufferType.INPUT: input_buffer,
            BufferType.OUTPUT: output_buffer,
        },
        camera_feeds=camera_feeds,
        current_reading_ma=35.0 + random.uniform(-5, 5),
        message=message,
        telemetry=_append_telemetry(counter, logger=logger),
        gantry_position=(150.0 + counter * 0.5, 80.0, 12.0),
    )
