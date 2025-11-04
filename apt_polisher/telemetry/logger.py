"""Simple CSV telemetry logger."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Optional

from apt_polisher.telemetry.series import TelemetryRecord


class TelemetryLogger:
    """Append-only CSV logger for telemetry data."""

    def __init__(self, path: Path, write_header: bool = True) -> None:
        self.path = path
        self._file = None
        self._writer = None
        self._write_header = write_header

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.exists()
        self._file = self.path.open("a", newline="")
        self._writer = csv.writer(self._file)
        if self._write_header and not exists:
            self._writer.writerow(["timestamp", "voltage", "current", "temperature"])

    def close(self) -> None:
        if self._file:
            self._file.close()
        self._file = None
        self._writer = None

    def log(self, record: TelemetryRecord) -> None:
        if not self._writer:
            self.open()
        self._writer.writerow([
            f"{record.timestamp:.3f}",
            "" if record.voltage is None else f"{record.voltage:.6f}",
            "" if record.current is None else f"{record.current:.6f}",
            "" if record.temperature is None else f"{record.temperature:.3f}",
        ])
        self._file.flush()

    def log_many(self, records: Iterable[TelemetryRecord]) -> None:
        for record in records:
            self.log(record)
