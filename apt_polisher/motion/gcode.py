import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

def make_sine_z_gcode(
    center_z: float,
    amplitude: float,
    period_s: float,
    duration_s: Optional[float] = None,
    cycles: Optional[int] = None,
    sample_hz: int = 50,
    start_phase_deg: float = 0.0,
    use_inverse_time: bool = True,
    z_min: Optional[float] = None,
    z_max: Optional[float] = None,
    precision: int = 4,
    max_feed_mm_min: float = 3000.0,  # used only for G94 mode
) -> str:
    """
    Generate G-code that approximates a sinusoidal motion on Z:
      Z(t) = center_z + amplitude * sin(2π t / period_s + φ0)

    Args:
      center_z:      Center position in mm (absolute Z).
      amplitude:     Peak amplitude in mm.
      period_s:      Period of the sine in seconds.
      duration_s:    Total time to run in seconds (ignored if 'cycles' given).
      cycles:        Number of periods to run (overrides 'duration_s' if set).
      sample_hz:     Segment rate (e.g., 50 -> 20 ms per segment).
      start_phase_deg: Starting phase (degrees).
      use_inverse_time: If True, emits G93 inverse-time feed for exact timing.
      z_min, z_max:  Optional soft limits (mm). Motion is clamped if provided.
      precision:     Decimal places for coordinates.
      max_feed_mm_min: Cap feed in G94 mode to this value.

    Returns:
      Multi-line G-code string.
    """
    if cycles is not None:
        total_time_s = cycles * period_s
    elif duration_s is not None:
        total_time_s = duration_s
    else:
        raise ValueError("Provide either 'cycles' or 'duration_s'.")

    if sample_hz <= 0:
        raise ValueError("sample_hz must be > 0")

    dt = 1.0 / sample_hz
    n_steps = max(1, int(round(total_time_s / dt)))
    w = 2.0 * math.pi / period_s
    phi0 = math.radians(start_phase_deg)

    # Helpers
    def clamp_z(z):
        if z_min is not None:
            z = max(z_min, z)
        if z_max is not None:
            z = min(z_max, z)
        return z

    lines = []
    lines.append(f"(SINE Z MOTION center={center_z} amp={amplitude} T={period_s}s "
                 f"rate={sample_hz}Hz mode={'G93' if use_inverse_time else 'G94'})")
    lines.append("G21  (mm units)")
    lines.append("G90  (absolute positioning)")
    if use_inverse_time:
        lines.append("G93  (inverse time feed rate)")
        invF = 60.0 / dt  # 1/min so each segment lasts exactly dt seconds
    else:
        lines.append("G94  (units/min feed)")
        # A reasonable constant feed: peak speed of the sine
        v_peak_mm_s = abs(amplitude) * w  # mm/s
        const_feed = min(max_feed_mm_min, max(1.0, v_peak_mm_s * 60.0))

    # Move to initial Z on the sine
    z_prev = clamp_z(center_z + amplitude * math.sin(phi0))
    lines.append(f"G1 Z{z_prev:.{precision}f}" + (f" F{const_feed:.2f}" if not use_inverse_time else ""))

    t = 0.0
    for _ in range(1, n_steps + 1):
        t += dt
        z_now = clamp_z(center_z + amplitude * math.sin(w * t + phi0))
        if use_inverse_time:
            # Inverse time: F is 1/min for THIS move; keep it constant so each segment takes dt seconds
            lines.append(f"G1 Z{z_now:.{precision}f} F{invF:.2f}")
        else:
            # Regular feed: make the segment take ~dt seconds by setting F per segment
            dz = abs(z_now - z_prev)
            # Avoid zero/very small dz -> pick tiny move feed
            feed = const_feed if dz < 1e-6 else min(max_feed_mm_min, max(1.0, (dz / dt) * 60.0))
            lines.append(f"G1 Z{z_now:.{precision}f} F{feed:.2f}")
        z_prev = z_now

    # Return controller to normal feed mode if we switched to G93
    if use_inverse_time:
        lines.append("G94 (back to units/min)")

    return "\n".join(lines)



def save_ngc(gcode: str,
             path: Optional[str] = None,
             overwrite: bool = False,
             add_eof: bool = True) -> str:
    """
    Save a G-code string to a .ngc file.
    """
    # Choose a default path if none provided
    if path is None:
        output_dir = Path("gcode")
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"program_{ts}.ngc"
    else:
        path = Path(path)
        if path.suffix.lower() != ".ngc":
            path = path.with_suffix(".ngc")

    # Normalize newlines to LF and ensure program end
    text = gcode.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    if add_eof:
        last = (text.splitlines()[-1].strip().upper() if text else "")
        if last not in {"M2", "M30", "%"}:
            text += "\nM2"
    text += "\n"  # final newline

    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; set overwrite=True to replace it.")

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)

    return str(path.resolve())
