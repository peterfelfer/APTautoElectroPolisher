from pathlib import Path

from apt_polisher.motion import make_sine_z_gcode, save_ngc


def test_make_sine_z_gcode_uses_z_axis():
    gcode = make_sine_z_gcode(
        center_z=0.0,
        amplitude=1.0,
        period_s=2.0,
        cycles=1,
        sample_hz=2,
        use_inverse_time=True,
    )
    moves = [line for line in gcode.splitlines() if line.startswith("G1")]
    assert moves, "Expected at least one motion command."
    assert all("Z" in move for move in moves)
    assert all(" X" not in move and not move.startswith("G1 X") for move in moves)


def test_save_ngc_creates_parent_dir(tmp_path: Path):
    target = tmp_path / "nested" / "program"
    gcode = "G90\nM2"
    output = save_ngc(gcode, path=target, overwrite=False)
    assert Path(output).exists()
    assert output.endswith(".ngc")
