"""Telemetry plotting widget embedded in Qt."""

from __future__ import annotations

import collections
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from apt_polisher.telemetry import TelemetrySeries


class TelemetryPlot(QWidget):
    """Embeds a Matplotlib plot that shows voltage/current/temperature traces."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._series: Optional[TelemetrySeries] = None

        self._figure = Figure(figsize=(8, 5))
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout()
        layout.addWidget(self._canvas)
        self.setLayout(layout)

        self._ax_main = self._figure.add_subplot(211)
        self._ax_temp = self._figure.add_subplot(212, sharex=self._ax_main)

        self._ax_main.set_ylabel("Voltage [V] & Current [A]")
        self._ax_temp.set_ylabel("Temp [°C]")
        self._ax_temp.set_xlabel("Time [s]")

        self._ax_main.grid(True, linestyle="--", linewidth=0.3)
        self._ax_temp.grid(True, linestyle="--", linewidth=0.3)

        self._voltage_line = self._ax_main.plot([], [], color="tab:blue", label="Voltage")[0]
        self._current_line = self._ax_main.plot([], [], color="tab:orange", label="Current")[0]
        self._temp_line = self._ax_temp.plot([], [], color="tab:green", label="Temperature")[0]

        self._ax_main.legend(loc="upper right")
        self._ax_temp.legend(loc="upper right")

        self._figure.tight_layout()

    def set_series(self, series: TelemetrySeries) -> None:
        self._series = series
        self.refresh()

    def refresh(self) -> None:
        if not self._series:
            return
        data = self._series.to_dict_of_lists()
        timestamps = data["timestamp"]
        self._voltage_line.set_data(timestamps, data["voltage"])
        self._current_line.set_data(timestamps, data["current"])
        self._temp_line.set_data(timestamps, data["temperature"])

        if timestamps:
            x_min, x_max = min(timestamps), max(timestamps)
            if x_min == x_max:
                x_max = x_min + 1.0
            self._ax_main.set_xlim(x_min, x_max)
            self._ax_temp.set_xlim(x_min, x_max)

        def _set_limits(axis, values):
            finite_values = [v for v in values if v == v]
            if finite_values:
                y_min, y_max = min(finite_values), max(finite_values)
                if y_min == y_max:
                    delta = max(1.0, abs(y_min) * 0.1 + 0.1)
                    y_min -= delta
                    y_max += delta
                axis.set_ylim(y_min * 0.95, y_max * 1.05)

        _set_limits(self._ax_main, data["voltage"] + data["current"])
        _set_limits(self._ax_temp, data["temperature"])

        self._canvas.draw_idle()
