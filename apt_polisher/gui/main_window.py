"""Qt-based main window for monitoring and controlling the electropolisher."""

from __future__ import annotations

import itertools
import math
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from apt_polisher.gui.model import BufferStatus, BufferType, CameraFrame, MachineSnapshot, MachineStatus
from apt_polisher.gui.widgets import TelemetryPlot
from apt_polisher.io import load_settings, update_settings_value
from apt_polisher.recipes import RecipeLoader


# ---------------------------------------------------------------------------
# Layout constants
WINDOW_DEFAULT_SIZE = (1600, 1000)

CAMERA_FEED_MIN_WIDTH = 240
CAMERA_FEED_MIN_HEIGHT = 240

MANUAL_JOG_MIN_STEP = 0.01
MANUAL_JOG_MAX_STEP = 10.0
MANUAL_JOG_DEFAULT_STEP = 1.0
MANUAL_JOG_DECIMALS = 3
MANUAL_JOG_SINGLE_STEP = 0.01
MANUAL_JOG_SLIDER_RANGE = (0, 100)
MANUAL_TARGET_RANGE = (-1000.0, 1000.0)
MANUAL_TARGET_DECIMALS = 3
MANUAL_TARGET_SINGLE_STEP = 0.1
MANUAL_LAYOUT_SPACING = 8

RECIPE_GLOBAL_LABEL = "Global Recipe"
RECIPE_SLOT_LABEL = "Input Slot Recipes"

SETUP_POSITION_UNKNOWN = "Current position: X=-- mm, Y=-- mm, Z=-- mm"

RIGHT_PANEL_CAMERA_STRETCH = 2
RIGHT_PANEL_BUFFERS_STRETCH = 1


class ControlPane(QWidget):
    """Control buttons to manage the workflow lifecycle."""

    start_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")

        layout = QHBoxLayout()
        layout.addWidget(self.start_btn)
        layout.addWidget(self.pause_btn)
        layout.addWidget(self.stop_btn)
        layout.addStretch()
        self.setLayout(layout)

        self.start_btn.clicked.connect(self.start_requested.emit)
        self.pause_btn.clicked.connect(self.pause_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)

    def update_state(self, status: MachineStatus) -> None:
        is_running = status == MachineStatus.RUNNING
        is_paused = status == MachineStatus.PAUSED
        self.start_btn.setEnabled(status in {MachineStatus.IDLE, MachineStatus.PAUSED, MachineStatus.WAITING_INPUT, MachineStatus.WAITING_OUTPUT})
        self.pause_btn.setEnabled(is_running)
        self.stop_btn.setEnabled(is_running or is_paused)


class BufferPane(QGroupBox):
    """Displays buffer occupancy in a table."""

    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Slot", "Occupied", "Specimen"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        self.setLayout(layout)

    def update_buffer(self, status: BufferStatus) -> None:
        self.table.setRowCount(status.capacity())
        for idx, slot in enumerate(status.slots):
            slot_item = QTableWidgetItem(str(slot.index))
            slot_item.setTextAlignment(Qt.AlignCenter)
            occupied_item = QTableWidgetItem("Yes" if slot.occupied else "No")
            occupied_item.setTextAlignment(Qt.AlignCenter)
            specimen_label = slot.specimen_id or "-"
            specimen_item = QTableWidgetItem(specimen_label)
            if slot.in_process:
                specimen_item.setText(f"{specimen_label} (processing)")

            for col, item in enumerate([slot_item, occupied_item, specimen_item]):
                self.table.setItem(idx, col, item)

        self.table.resizeColumnsToContents()


class CameraFeedWidget(QWidget):
    """Widget that displays scrub-able frames for one camera feed."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.frames: List[CameraFrame] = []
        self.show_analysis = False

        self.title_label = QLabel(name)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.image_label = QLabel("(no image)")
        self.image_label.setMinimumSize(CAMERA_FEED_MIN_WIDTH, CAMERA_FEED_MIN_HEIGHT)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.setVisible(False)

        self.toggle_btn = QPushButton("Show Analysis Overlay")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._on_toggle_analysis)
        self.toggle_btn.setVisible(False)

        layout = QVBoxLayout()
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.slider)
        layout.addWidget(self.toggle_btn)
        layout.addStretch()
        self.setLayout(layout)

    def set_frames(self, frames: List[CameraFrame]) -> None:
        self.frames = frames
        count = len(frames)
        self.slider.setVisible(count > 1)
        if count > 0:
            self.slider.blockSignals(True)
            self.slider.setRange(0, count - 1)
            self.slider.setValue(count - 1)
            self.slider.blockSignals(False)
        has_analysis = any(frame.analysis_path for frame in frames)
        self.toggle_btn.blockSignals(True)
        if not has_analysis:
            self.toggle_btn.setChecked(False)
            self.toggle_btn.setText("Show Analysis Overlay")
        self.toggle_btn.setVisible(has_analysis)
        self.toggle_btn.setEnabled(has_analysis)
        self.toggle_btn.blockSignals(False)
        self.show_analysis = has_analysis and self.toggle_btn.isChecked()
        self._display_frame(self.slider.value() if count else 0)

    def _on_toggle_analysis(self, checked: bool) -> None:
        self.show_analysis = checked
        self.toggle_btn.setText("Show Raw Image" if checked else "Show Analysis Overlay")
        self._display_frame(self.slider.value())

    def _on_slider_changed(self, index: int) -> None:
        self._display_frame(index)

    def _display_frame(self, index: int) -> None:
        if not self.frames:
            self.image_label.setText("(no image)")
            return
        index = max(0, min(index, len(self.frames) - 1))
        frame = self.frames[index]
        path = frame.analysis_path if self.show_analysis and frame.analysis_path else frame.image_path
        if not path.exists():
            self.image_label.setText(f"(missing file)\n{path}")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.image_label.setText(f"(unreadable image)\n{path}")
            return
        self.image_label.setPixmap(pixmap.scaled(360, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class CameraPane(QGroupBox):
    """Displays the latest images from cameras with scrubbing controls."""

    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.widgets: Dict[str, CameraFeedWidget] = {}
        self.grid = QGridLayout()
        self.setLayout(self.grid)

    def update_feeds(self, feeds: Dict[str, List[CameraFrame]]) -> None:
        # Ensure consistent ordering
        for row, (name, frames) in enumerate(sorted(feeds.items())):
            if name not in self.widgets:
                widget = CameraFeedWidget(name)
                self.widgets[name] = widget
                self.grid.addWidget(widget, row, 0)
            self.widgets[name].set_frames(frames)


class GCodePane(QGroupBox):
    """Displays currently executing G-code."""

    def __init__(self) -> None:
        super().__init__("Active G-code")
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout = QVBoxLayout()
        layout.addWidget(self.text)
        self.setLayout(layout)

    def set_gcode(self, gcode: Optional[str]) -> None:
        self.text.setPlainText(gcode or "No program loaded.")


class StatusPane(QGroupBox):
    """Shows high-level machine status and metrics."""

    def __init__(self) -> None:
        super().__init__("Machine Status")
        self.status_label = QLabel("Status: Unknown")
        self.message_label = QLabel()
        self.current_label = QLabel("Current: n/a")

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.current_label)
        layout.addWidget(self.message_label)
        layout.addStretch()
        self.setLayout(layout)

    def update_snapshot(self, snapshot: MachineSnapshot) -> None:
        self.status_label.setText(f"Status: {snapshot.status.name.title()}")
        if snapshot.current_reading_ma is not None:
            self.current_label.setText(f"Current: {snapshot.current_reading_ma:.1f} mA")
        else:
            self.current_label.setText("Current: n/a")
        self.message_label.setText(snapshot.message or "")


class ManualControlPane(QGroupBox):
    """Provides jog and absolute move controls for the gantry."""

    jog_requested = Signal(float, float, float)
    move_requested = Signal(float, float, float)

    def __init__(self) -> None:
        super().__init__("Manual Motion")

        self._syncing_step = False
        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(MANUAL_JOG_MIN_STEP, MANUAL_JOG_MAX_STEP)
        self.step_spin.setDecimals(MANUAL_JOG_DECIMALS)
        self.step_spin.setSingleStep(MANUAL_JOG_SINGLE_STEP)
        self.step_spin.setValue(MANUAL_JOG_DEFAULT_STEP)

        self.step_slider = QSlider(Qt.Horizontal)
        self.step_slider.setMinimum(MANUAL_JOG_SLIDER_RANGE[0])
        self.step_slider.setMaximum(MANUAL_JOG_SLIDER_RANGE[1])
        self.step_slider.setValue(self._step_to_slider(self.step_spin.value()))

        self.step_slider.valueChanged.connect(self._on_slider_changed)
        self.step_spin.valueChanged.connect(self._on_step_changed)

        step_layout = QVBoxLayout()
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Jog step (mm):"))
        top_row.addWidget(self.step_spin)
        top_row.addStretch()
        step_layout.addLayout(top_row)
        step_layout.addWidget(self.step_slider)

        jog_grid = QGridLayout()
        axes = ("X", "Y", "Z")
        for row, axis in enumerate(axes):
            minus_btn = QPushButton(f"{axis}-")
            plus_btn = QPushButton(f"{axis}+")
            minus_btn.clicked.connect(lambda _, a=axis: self._emit_jog(a, -1))
            plus_btn.clicked.connect(lambda _, a=axis: self._emit_jog(a, 1))
            jog_grid.addWidget(minus_btn, row, 0)
            jog_grid.addWidget(plus_btn, row, 1)

        self.target_x = QDoubleSpinBox()
        self.target_y = QDoubleSpinBox()
        self.target_z = QDoubleSpinBox()
        for box in (self.target_x, self.target_y, self.target_z):
            box.setRange(*MANUAL_TARGET_RANGE)
            box.setDecimals(MANUAL_TARGET_DECIMALS)
            box.setSingleStep(MANUAL_TARGET_SINGLE_STEP)

        target_form = QFormLayout()
        target_form.addRow("X [mm]", self.target_x)
        target_form.addRow("Y [mm]", self.target_y)
        target_form.addRow("Z [mm]", self.target_z)

        move_btn = QPushButton("Move to Position")
        move_btn.clicked.connect(self._emit_move)

        layout = QVBoxLayout()
        layout.addLayout(step_layout)
        layout.addLayout(jog_grid)
        layout.addSpacing(MANUAL_LAYOUT_SPACING)
        layout.addLayout(target_form)
        layout.addWidget(move_btn)
        layout.addStretch()
        self.setLayout(layout)

    @staticmethod
    def _slider_to_step(value: int) -> float:
        slider_min, slider_max = MANUAL_JOG_SLIDER_RANGE
        fraction = (value - slider_min) / float(slider_max - slider_min)
        log_val = -2.0 + fraction * 3.0  # maps slider range to [-2,1]
        return 10 ** log_val

    @staticmethod
    def _step_to_slider(step: float) -> int:
        step_clamped = min(max(step, MANUAL_JOG_MIN_STEP), MANUAL_JOG_MAX_STEP)
        log_val = math.log10(step_clamped)
        fraction = (log_val + 2.0) / 3.0
        slider_min, slider_max = MANUAL_JOG_SLIDER_RANGE
        return int(round(slider_min + fraction * (slider_max - slider_min)))

    def _on_slider_changed(self, value: int) -> None:
        if self._syncing_step:
            return
        step = self._slider_to_step(value)
        self._syncing_step = True
        self.step_spin.setValue(step)
        self._syncing_step = False

    def _on_step_changed(self, value: float) -> None:
        if self._syncing_step:
            return
        slider_value = self._step_to_slider(value)
        self._syncing_step = True
        self.step_slider.setValue(slider_value)
        self._syncing_step = False

    def _emit_jog(self, axis: str, direction: int) -> None:
        step = self.step_spin.value() * direction
        dx = dy = dz = 0.0
        if axis == "X":
            dx = step
        elif axis == "Y":
            dy = step
        else:
            dz = step
        self.jog_requested.emit(dx, dy, dz)

    def _emit_move(self) -> None:
        self.move_requested.emit(
            self.target_x.value(),
            self.target_y.value(),
            self.target_z.value(),
        )


class SetupPane(QGroupBox):
    """Allows recording of key positions while viewing current gantry coordinates."""

    record_requested = Signal(str, float, float, float)
    thickness_calibration_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Setup Mode")
        self.position_label = QLabel(SETUP_POSITION_UNKNOWN)
        self._current_position: Optional[Tuple[float, float, float]] = None

        settings = load_settings()
        buffers = settings.get("buffers", {})
        input_slots = buffers.get("input_slots", [])
        output_slots = buffers.get("output_slots", [])
        camera_positions = settings.get("camera_positions", {})
        fixed_positions = settings.get("positions", {})

        layout = QVBoxLayout()
        layout.addWidget(self.position_label)

        def add_button_section(title: str, entries):
            if not entries:
                return
            layout.addWidget(QLabel(title))
            grid = QGridLayout()
            for idx, (label, identifier) in enumerate(entries):
                btn = QPushButton(label)
                btn.clicked.connect(lambda _, ident=identifier: self._handle_record(ident))
                grid.addWidget(btn, idx // 2, idx % 2)
            layout.addLayout(grid)

        input_entries = [
            (f"Input Slot {slot.get('slot', index + 1)}", f"buffers.input_slots[{index}]")
            for index, slot in enumerate(input_slots)
        ]
        output_entries = [
            (f"Output Slot {slot.get('slot', index + 1)}", f"buffers.output_slots[{index}]")
            for index, slot in enumerate(output_slots)
        ]
        camera_entries = []
        if camera_positions:
            if "microscope_xyz" in camera_positions:
                camera_entries.append(("Microscope", "camera_positions.microscope_xyz"))
            if "overview_xyz" in camera_positions:
                camera_entries.append(("Overview", "camera_positions.overview_xyz"))
        fixed_entries = []
        if fixed_positions:
            if "beaker_xyz" in fixed_positions:
                fixed_entries.append(("Beaker", "positions.beaker_xyz"))
            if "polishing_zero_xyz" in fixed_positions:
                fixed_entries.append(("Polishing Zero", "positions.polishing_zero_xyz"))

        add_button_section("Input Buffer Slots", input_entries)
        add_button_section("Output Buffer Slots", output_entries)
        add_button_section("Camera Targets", camera_entries)
        add_button_section("Process Positions", fixed_entries)

        thickness_btn = QPushButton("Calibrate Thickness")
        thickness_btn.clicked.connect(self.thickness_calibration_requested)
        layout.addWidget(thickness_btn)

        layout.addStretch()
        self.setLayout(layout)

    def update_position(self, position: Optional[Tuple[float, float, float]]) -> None:
        if position is None:
            self.position_label.setText(SETUP_POSITION_UNKNOWN)
            self._current_position = None
        else:
            x, y, z = position
            self.position_label.setText(f"Current position: X={x:.3f} mm, Y={y:.3f} mm, Z={z:.3f} mm")
            self._current_position = (x, y, z)

    def _handle_record(self, identifier: str) -> None:
        if self._current_position is None:
            QMessageBox.warning(
                self,
                "Position Unknown",
                "Current gantry position is not available. Move the gantry or wait for telemetry updates before recording.",
            )
            return
        x, y, z = self._current_position
        self.record_requested.emit(identifier, x, y, z)


class RecipePane(QGroupBox):
    """Displays global and per-slot recipe dropdowns."""

    global_recipe_changed = Signal(str)
    slot_recipe_changed = Signal(int, str)

    def __init__(self, recipes: List[str], slots: List[int], default_recipe: Optional[str] = None) -> None:
        super().__init__("Recipes")
        self._recipes = recipes or ["<none>"]
        self._slots = slots
        self._slot_combos: Dict[int, QComboBox] = {}

        layout = QVBoxLayout()

        self.global_combo = QComboBox()
        self.global_combo.addItems(self._recipes)
        if default_recipe and default_recipe in self._recipes:
            self.global_combo.setCurrentText(default_recipe)
        self.global_combo.currentTextChanged.connect(self.global_recipe_changed)

        layout.addWidget(QLabel(RECIPE_GLOBAL_LABEL))
        layout.addWidget(self.global_combo)

        if slots:
            layout.addWidget(QLabel(RECIPE_SLOT_LABEL))
            for slot in slots:
                row = QHBoxLayout()
                row.addWidget(QLabel(f"Slot {slot}"))
                combo = QComboBox()
                combo.addItems(self._recipes)
                combo.currentTextChanged.connect(lambda name, s=slot: self.slot_recipe_changed.emit(s, name))
                row.addWidget(combo)
                layout.addLayout(row)
                self._slot_combos[slot] = combo

        layout.addStretch()
        self.setLayout(layout)

    def update_recipes(self, recipes: List[str]) -> None:
        if not recipes:
            return
        self._recipes = recipes
        self.global_combo.blockSignals(True)
        self.global_combo.clear()
        self.global_combo.addItems(recipes)
        self.global_combo.blockSignals(False)
        for slot, combo in self._slot_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(recipes)
            combo.blockSignals(False)

    def set_slot_recipe(self, slot: int, recipe_name: str) -> None:
        combo = self._slot_combos.get(slot)
        if combo and recipe_name in self._recipes:
            combo.blockSignals(True)
            combo.setCurrentText(recipe_name)
            combo.blockSignals(False)
class MainWindow(QMainWindow):
    """Main UI window coordinating panes."""

    start_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    jog_requested = Signal(float, float, float)
    move_requested = Signal(float, float, float)
    record_position_requested = Signal(str, float, float, float)
    global_recipe_selected = Signal(str)
    slot_recipe_selected = Signal(int, str)

    def __init__(self, enable_setup: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("APT Electropolisher")
        self.resize(*WINDOW_DEFAULT_SIZE)
        
        self._settings = load_settings()
        self.recipe_loader = RecipeLoader()
        recipes = self.recipe_loader.list() or ["default"]
        slots = self._input_slot_ids()

        self.control_pane = ControlPane()
        self.status_pane = StatusPane()
        self.gcode_pane = GCodePane()
        self.telemetry_plot = TelemetryPlot()
        self.camera_pane = CameraPane("Latest Camera Images")
        self.input_buffer_pane = BufferPane("Input Buffer")
        self.output_buffer_pane = BufferPane("Output Buffer")
        self.manual_control = ManualControlPane()
        self.setup_pane: Optional[SetupPane] = SetupPane() if enable_setup else None
        self.recipe_pane = RecipePane(recipes, slots, default_recipe=recipes[0] if recipes else None)

        left_splitter = QSplitter(Qt.Vertical)
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.status_pane)
        left_layout.addWidget(self.gcode_pane)
        left_layout.addWidget(self.telemetry_plot)
        left_layout.addWidget(self.control_pane)
        left_layout.addWidget(self.recipe_pane)
        left_layout.addWidget(self.manual_control)
        if self.setup_pane:
            left_layout.addWidget(self.setup_pane)
        left_layout.addStretch()
        left_widget.setLayout(left_layout)

        right_widget = QWidget()
        right_layout = QHBoxLayout()

        buffers_widget = QWidget()
        buffers_layout = QVBoxLayout()
        buffers_layout.addWidget(self.input_buffer_pane)
        buffers_layout.addWidget(self.output_buffer_pane)
        buffers_layout.addStretch()
        buffers_widget.setLayout(buffers_layout)

        right_layout.addWidget(self.camera_pane, stretch=RIGHT_PANEL_CAMERA_STRETCH)
        right_layout.addWidget(buffers_widget, stretch=RIGHT_PANEL_BUFFERS_STRETCH)
        right_widget.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        central = QWidget()
        central_layout = QVBoxLayout()
        central_layout.addWidget(splitter)
        central.setLayout(central_layout)

        self.setCentralWidget(central)

        # Relay control signals outward
        self.control_pane.start_requested.connect(self.start_requested)
        self.control_pane.pause_requested.connect(self.pause_requested)
        self.control_pane.stop_requested.connect(self.stop_requested)
        self.manual_control.jog_requested.connect(self.jog_requested)
        self.manual_control.move_requested.connect(self.move_requested)
        self.recipe_pane.global_recipe_changed.connect(self.global_recipe_selected)
        self.recipe_pane.slot_recipe_changed.connect(self.slot_recipe_selected)
        if self.setup_pane:
            self.setup_pane.record_requested.connect(self.record_position_requested)
            self.setup_pane.thickness_calibration_requested.connect(
                lambda: QMessageBox.information(
                    self,
                    "Thickness Calibration",
                    "Launch thickness calibration workflow (not yet implemented).",
                )
            )

    @Slot(MachineSnapshot)
    def update_snapshot(self, snapshot: MachineSnapshot) -> None:
        self.status_pane.update_snapshot(snapshot)
        self.control_pane.update_state(snapshot.status)
        self.gcode_pane.set_gcode(snapshot.active_gcode)
        if snapshot.telemetry:
            self.telemetry_plot.set_series(snapshot.telemetry)
            self.telemetry_plot.refresh()
        if self.setup_pane:
            self.setup_pane.update_position(snapshot.gantry_position)

    # ------------------------------------------------------------------
    def _input_slot_ids(self) -> List[int]:
        slots = self._settings.get("buffers", {}).get("input_slots", [])
        ids = []
        for entry in slots:
            slot = entry.get("slot")
            if isinstance(slot, int):
                ids.append(slot)
        if not ids:
            ids = list(range(1, len(slots) + 1))
        return sorted(ids)

        input_status = snapshot.buffers.get(BufferType.INPUT)
        if input_status:
            self.input_buffer_pane.update_buffer(input_status)
        output_status = snapshot.buffers.get(BufferType.OUTPUT)
        if output_status:
            self.output_buffer_pane.update_buffer(output_status)

        self.camera_pane.update_feeds(snapshot.camera_feeds)


def run_gui(snapshot_provider, snapshot_interval_ms: int = 500, enable_setup: bool = False) -> None:
    """Launch the GUI and periodically request snapshots from the provider callable."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow(enable_setup=enable_setup)

    def refresh() -> None:
        snapshot = snapshot_provider()
        if snapshot is None:
            return
        window.update_snapshot(snapshot)

    timer = QTimer()
    timer.timeout.connect(refresh)
    timer.start(snapshot_interval_ms)

    window.start_requested.connect(lambda: QMessageBox.information(window, "Start", "Start requested (wire this to infrastructure)."))
    window.pause_requested.connect(lambda: QMessageBox.information(window, "Pause", "Pause requested (wire this to infrastructure)."))
    window.stop_requested.connect(lambda: QMessageBox.information(window, "Stop", "Stop requested (wire this to infrastructure)."))
    window.jog_requested.connect(
        lambda dx, dy, dz: QMessageBox.information(
            window,
            "Jog Requested",
            f"Jog by ΔX={dx:.3f} mm, ΔY={dy:.3f} mm, ΔZ={dz:.3f} mm (hook up to motion control)",
        )
    )
    window.move_requested.connect(
        lambda x, y, z: QMessageBox.information(
            window,
            "Move Requested",
            f"Move to X={x:.3f} mm, Y={y:.3f} mm, Z={z:.3f} mm (hook up to motion control)",
        )
    )
    window.global_recipe_selected.connect(lambda name: QMessageBox.information(window, "Recipe", f"Global recipe set to '{name}'. Integrate with workflow queue."))
    window.slot_recipe_selected.connect(lambda slot, name: QMessageBox.information(window, "Slot Recipe", f"Slot {slot} recipe set to '{name}'. Integrate with workflow queue."))
    if enable_setup:
        def handle_record(identifier: str, x: float, y: float, z: float) -> None:
            coords = [round(x, 3), round(y, 3), round(z, 3)]
            try:
                update_settings_value(identifier, coords)
            except Exception as exc:
                QMessageBox.critical(
                    window,
                    "Save Failed",
                    f"Could not update settings for '{identifier}': {exc}",
                )
            else:
                QMessageBox.information(
                    window,
                    "Position Saved",
                    f"Updated {identifier} to {coords} in settings.yml",
                )

        window.record_position_requested.connect(handle_record)

    window.show()
    refresh()
    app.exec()
