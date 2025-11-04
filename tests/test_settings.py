from pathlib import Path

import yaml

from apt_polisher.io import load_polishing_settings, load_settings, update_settings_value


def test_default_settings_structure():
    data = load_settings()
    assert "cnc" in data
    assert "power_supply" in data
    assert "cameras" in data
    assert "buffers" in data and len(data["buffers"]["input_slots"]) >= 5
    assert len(data["buffers"]["output_slots"]) >= 5
    first_input = data["buffers"]["input_slots"][0]
    assert "position" in first_input and len(first_input["position"]) == 3
    assert "camera_positions" in data and "microscope_xyz" in data["camera_positions"]
    assert "positions" in data and "beaker_xyz" in data["positions"]
    assert "calibration" in data and "thickness" in data["calibration"]


def test_default_polishing_settings_structure():
    data = load_polishing_settings()
    assert "waveform" in data
    assert "process" in data
    assert "motion" in data


def test_update_settings_value(tmp_path: Path):
    sample = {
        "buffers": {"input_slots": [{"slot": 1, "position": [0.0, 0.0, 0.0]}]},
        "camera_positions": {"microscope_xyz": [1.0, 2.0, 3.0]},
    }
    settings_path = tmp_path / "settings.yml"
    settings_path.write_text(yaml.safe_dump(sample))

    update_settings_value("buffers.input_slots[0].position", [5.0, 6.0, 7.0], settings_path)
    update_settings_value("camera_positions.microscope_xyz", [8.0, 9.0, 10.0], settings_path)

    data = yaml.safe_load(settings_path.read_text())
    assert data["buffers"]["input_slots"][0]["position"] == [5.0, 6.0, 7.0]
    assert data["camera_positions"]["microscope_xyz"] == [8.0, 9.0, 10.0]
