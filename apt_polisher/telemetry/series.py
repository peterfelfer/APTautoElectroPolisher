"""In-memory telemetry series for plotting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, Iterator, List, Optional
from collections import deque


@dataclass
class TelemetryRecord:
    """Single telemetry data point."""

    timestamp: float
    voltage: Optional[float] = None
    current: Optional[float] = None
    temperature: Optional[float] = None


@dataclass
class TelemetrySeries:
    """Maintains a rolling window of telemetry data suitable for plotting."""

    max_points: int = 500
    _records: Deque[TelemetryRecord] = field(default_factory=deque)

    def append(self, record: TelemetryRecord) -> None:
        self._records.append(record)
        while len(self._records) > self.max_points:
            self._records.popleft()

    def extend(self, records: Iterable[TelemetryRecord]) -> None:
        for record in records:
            self.append(record)

    def __iter__(self) -> Iterator[TelemetryRecord]:
        return iter(self._records)

    def to_dict_of_lists(self) -> Dict[str, List[float]]:
        timestamps = []
        voltages = []
        currents = []
        temperatures = []
        for rec in self._records:
            timestamps.append(rec.timestamp)
            voltages.append(rec.voltage if rec.voltage is not None else float("nan"))
            currents.append(rec.current if rec.current is not None else float("nan"))
            temperatures.append(rec.temperature if rec.temperature is not None else float("nan"))
        return {
            "timestamp": timestamps,
            "voltage": voltages,
            "current": currents,
            "temperature": temperatures,
        }

    def latest(self) -> Optional[TelemetryRecord]:
        return self._records[-1] if self._records else None
