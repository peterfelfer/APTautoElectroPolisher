from pathlib import Path

import yaml

from apt_polisher.instrumentation import PowerSupply
from apt_polisher.orchestration.workflow import PolishingWorkflow, WorkflowConfig
from apt_polisher.sensors import DummyCurrentSensor


class DummyCNC:
    def __init__(self):
        self.commands = []

    def send_gcode(self, line: str) -> None:
        self.commands.append(line)

    def stream_gcode(self, lines, max_outstanding=12):
        self.commands.extend(list(lines))

    def wait_until_idle(self, *args, **kwargs):
        return


def build_fixture_dir(tmp_path: Path) -> None:
    (tmp_path / "recipes" / "motion").mkdir(parents=True)
    (tmp_path / "recipes" / "motion" / "pickup_standard.gcode").write_text("G1 X1\n")
    (tmp_path / "recipes" / "motion" / "place_standard.gcode").write_text("G1 X-1\n")
    (tmp_path / "recipes" / "motion" / "cleaning_cycle.gcode").write_text("G4 P1\n")
    recipe_path = tmp_path / "recipes" / "default.yml"
    recipe_path.write_text(
        """
metadata:
  description: Test recipe
motion:
  safe_z_mm: 20
  pickup_macro: pickup_standard
  place_macro: place_standard
motion_macros:
  pickup_standard:
    file: motion/pickup_standard.gcode
  place_standard:
    file: motion/place_standard.gcode
polishing:
  waveform:
    amplitude_mm: 0.2
    period_s: 1.0
    center_z_mm: -0.5
  contact:
    approach_speed_mm_s: 1.0
    detection_current_ma: 1.0
    max_depth_mm: 1.0
  cycle:
    mode: cycles
    max_cycles: 1
    duration_s: 10
  voltage_v: 6.0
  current_limit_a: 0.4
cleaning:
  rinse_cycles: 1
imaging:
  thickness_threshold_um: 300
        """
    )

    settings = {
        "buffers": {
            "input_slots": [
                {"slot": 1, "position": [100.0, 50.0, 5.0]},
            ],
            "output_slots": [
                {"slot": 1, "position": [120.0, 60.0, 5.0]},
            ],
        },
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yml").write_text(yaml.safe_dump(settings))


def test_workflow_runs_with_recipe(tmp_path, monkeypatch):
    build_fixture_dir(tmp_path)
    monkeypatch.setattr("apt_polisher.io.settings.find_project_root", lambda: tmp_path)
    monkeypatch.setattr("apt_polisher.recipes.loader.find_project_root", lambda: tmp_path)
    monkeypatch.setattr("apt_polisher.motion.macros.find_project_root", lambda: tmp_path)

    cnc = DummyCNC()
    sensor = DummyCurrentSensor()
    workflow = PolishingWorkflow(
        cnc=cnc,
        current_sensor=sensor,
        vision=None,
        power_supply=None,
        config=WorkflowConfig(storage_slot=1, default_recipe="default"),
    )
    workflow.enqueue_slot(1)
    workflow.run()

    assert any("pickup" in cmd.lower() or "G1 X1" in cmd for cmd in cnc.commands)
    assert any("G0" in cmd or "G1" in cmd for cmd in cnc.commands)
