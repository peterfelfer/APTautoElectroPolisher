"""High-level orchestration for moving specimens through the polishing cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Tuple

from apt_polisher.io import load_settings
from apt_polisher.motion import FluidNCClient, MacroRunner
from apt_polisher.recipes import Recipe, RecipeLoader
from apt_polisher.sensors import CurrentSensor
from apt_polisher.instrumentation import PowerSupply


class VisionSystem(Protocol):
    """Minimal interface for vision subsystems used during the workflow."""

    def capture_snapshot(self, label: Optional[str] = None) -> None:
        ...


@dataclass
class WorkflowConfig:
    """Parameters for the polishing workflow."""

    storage_slot: int
    polishing_cycles: int = 1
    imaging_interval_s: float = 30.0
    default_recipe: str = "default"


class PolishingWorkflow:
    """Coordinates motion control, imaging, and sensing for one specimen."""

    def __init__(
        self,
        cnc: FluidNCClient,
        current_sensor: CurrentSensor,
        vision: Optional[VisionSystem] = None,
        power_supply: Optional[PowerSupply] = None,
        config: Optional[WorkflowConfig] = None,
        recipe_loader: Optional[RecipeLoader] = None,
    ) -> None:
        self.cnc = cnc
        self.current_sensor = current_sensor
        self.vision = vision
        self.config = config or WorkflowConfig(storage_slot=0)
        self.power_supply = power_supply
        self.recipe_loader = recipe_loader or RecipeLoader()
        self.macro_runner = MacroRunner()
        self._settings_cache = load_settings()

        # Slot index -> recipe name
        self._job_queue: List[Tuple[int, str]] = []

    # ------------------------------------------------------------------
    # Job management
    def enqueue_slot(self, slot_index: int, recipe_name: Optional[str] = None) -> None:
        name = recipe_name or self.config.default_recipe
        self._job_queue.append((slot_index, name))

    def clear_queue(self) -> None:
        self._job_queue.clear()

    def available_recipes(self) -> List[str]:
        return self.recipe_loader.list()

    # ------------------------------------------------------------------
    def run(self) -> None:
        """Process all queued specimens sequentially."""
        while self._job_queue:
            slot_index, recipe_name = self._job_queue.pop(0)
            recipe = self.recipe_loader.load(recipe_name)
            self._process_specimen(slot_index, recipe)

    # ------------------------------------------------------------------
    def _process_specimen(self, slot_index: int, recipe: Recipe) -> None:
        self._move_to_safe_z(recipe.safe_z_mm)
        self._pickup_specimen(slot_index, recipe)
        self._move_to_safe_z(recipe.safe_z_mm)
        self._perform_contact(recipe)
        self._polish_cycles(recipe)
        self._inspect_and_repeat(recipe)
        self._finish_and_store(slot_index, recipe)

    # ------------------------------------------------------------------
    def _move_to_safe_z(self, safe_z: float) -> None:
        self.cnc.send_gcode(f"G90")
        self.cnc.send_gcode(f"G1 Z{safe_z:.3f} F600")
        self.cnc.wait_until_idle()

    def _pickup_specimen(self, slot_index: int, recipe: Recipe) -> None:
        position = self._slot_position("input_slots", slot_index)
        self._rapid_xy(position[:2], safe_z=self.configured_safe_z(recipe))
        macro = recipe.motion_macros.get(recipe.pickup_macro)
        if macro is None:
            raise RuntimeError(f"Recipe '{recipe.name}' missing pickup macro '{recipe.pickup_macro}'")
        self.macro_runner.execute(self.cnc, macro)

    def _perform_contact(self, recipe: Recipe) -> None:
        # Placeholder implementation: descend to contact depth using simple loop
        contact_cfg = recipe.contact
        approach_speed = contact_cfg.get("approach_speed_mm_s", 1.0)
        calibration_contact = self._settings_cache.get("calibration", {}).get("contact", {})
        step_mm = calibration_contact.get("approach_step_mm", contact_cfg.get("approach_step_mm", 0.1))
        max_depth = contact_cfg.get("max_depth_mm", 5.0)
        target_current_ma = contact_cfg.get("detection_current_ma", 5.0)
        retract_mm = calibration_contact.get("retract_mm", 2.0)

        depth = 0.0
        self.cnc.send_gcode("G91")
        while depth < max_depth:
            self.cnc.send_gcode(f"G1 Z-{step_mm:.3f} F{approach_speed * 60:.1f}")
            self.cnc.wait_until_idle()
            depth += step_mm
            reading = self.current_sensor.read().amperes * 1000.0
            if reading >= target_current_ma:
                break
        if retract_mm > 0:
            self.cnc.send_gcode(f"G1 Z{retract_mm:.3f} F{approach_speed * 60:.1f}")
            self.cnc.wait_until_idle()
        self.cnc.send_gcode("G90")

    def _polish_cycles(self, recipe: Recipe) -> None:
        cycle_cfg = recipe.polishing_cycle
        duration_s = cycle_cfg.duration_s or 60.0
        max_cycles = cycle_cfg.max_cycles or 5
        waveform = recipe.polishing_waveform
        gcode = make_polishing_waveform(waveform)
        for _ in range(max_cycles):
            self.cnc.stream_gcode(gcode)
            self.cnc.wait_until_idle()
            # Placeholder timing: in real implementation, wait for duration and monitor telemetry

    def _inspect_and_repeat(self, recipe: Recipe) -> None:
        # Placeholder for imaging loop – would integrate vision analysis and thresholds
        if self.vision:
            self.vision.capture_snapshot("inspection")

    def _finish_and_store(self, slot_index: int, recipe: Recipe) -> None:
        self._move_to_safe_z(recipe.safe_z_mm)
        macro = recipe.motion_macros.get(recipe.place_macro)
        if macro is None:
            raise RuntimeError(f"Recipe '{recipe.name}' missing place macro '{recipe.place_macro}'")
        output_slot = self._next_free_output_slot()
        if output_slot is None:
            raise RuntimeError("No free output slot available")
        position = self._slot_position("output_slots", output_slot)
        self._rapid_xy(position[:2], safe_z=self.configured_safe_z(recipe))
        self.macro_runner.execute(self.cnc, macro)

    # ------------------------------------------------------------------
    def configured_safe_z(self, recipe: Recipe) -> float:
        positions = self._settings_cache.get("positions", {})
        return float(positions.get("safe_z_mm", recipe.safe_z_mm))

    def _rapid_xy(self, xy: List[float], safe_z: float) -> None:
        self.cnc.send_gcode("G90")
        self.cnc.send_gcode(f"G0 Z{safe_z:.3f}")
        self.cnc.send_gcode(f"G0 X{xy[0]:.3f} Y{xy[1]:.3f}")
        self.cnc.wait_until_idle()

    def _slot_position(self, slot_type: str, slot_index: int) -> List[float]:
        slots = self._settings_cache.get("buffers", {}).get(slot_type, [])
        for entry in slots:
            if entry.get("slot") == slot_index:
                return entry.get("position", [0.0, 0.0, 0.0])
        # Fallback to positional index (1-based)
        if 0 < slot_index <= len(slots):
            return slots[slot_index - 1].get("position", [0.0, 0.0, 0.0])
        raise RuntimeError(f"Slot {slot_index} not defined for {slot_type}")

    def _next_free_output_slot(self) -> Optional[int]:
        slots = self._settings_cache.get("buffers", {}).get("output_slots", [])
        for entry in slots:
            slot_id = entry.get("slot")
            if entry.get("specimen", None) is None:
                return slot_id or slots.index(entry) + 1
        return None


def make_polishing_waveform(waveform_cfg: Dict[str, float]) -> List[str]:
    """Generate a simple oscillation G-code list based on recipe configuration."""
    center = waveform_cfg.get("center_z_mm", 0.0)
    amplitude = waveform_cfg.get("amplitude_mm", 0.5)
    period = waveform_cfg.get("period_s", 2.0)
    # Placeholder: apply small two-point waveform
    up = center + amplitude
    down = center - amplitude
    return [
        "G91",
        f"G1 Z{up:.3f} F300",
        f"G1 Z{down:.3f} F300",
        "G90",
    ]
