#!/usr/bin/env python3
"""CLI helper to generate polishing G-code waveforms."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from apt_polisher.motion import make_sine_z_gcode, save_ngc


def positive_float(value: str) -> float:
    try:
        val = float(value)
    except ValueError as exc:  # pragma: no cover - argparse handles message
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if val <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return val


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--center", type=float, required=True, help="Center Z position in mm.")
    parser.add_argument("--amplitude", type=positive_float, required=True, help="Peak amplitude in mm.")
    parser.add_argument("--period", type=positive_float, required=True, help="Sine period in seconds.")
    duration_group = parser.add_mutually_exclusive_group(required=True)
    duration_group.add_argument("--duration", type=positive_float, help="Total runtime in seconds.")
    duration_group.add_argument("--cycles", type=int, help="Number of sine cycles to execute.")
    parser.add_argument("--sample-hz", type=positive_float, default=50.0, help="Segment rate.")
    parser.add_argument("--start-phase", type=float, default=0.0, help="Starting phase in degrees.")
    parser.add_argument("--no-inverse-time", action="store_true", help="Emit G94 feed instead of G93.")
    parser.add_argument("--z-min", type=float, help="Clamp motion to this minimum Z (mm).")
    parser.add_argument("--z-max", type=float, help="Clamp motion to this maximum Z (mm).")
    parser.add_argument("--precision", type=int, default=4, help="Decimal precision for coordinates.")
    parser.add_argument("--output", type=Path, help="Optional target file path (.ngc).")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gcode = make_sine_z_gcode(
        center_z=args.center,
        amplitude=args.amplitude,
        period_s=args.period,
        duration_s=args.duration,
        cycles=args.cycles,
        sample_hz=int(args.sample_hz),
        start_phase_deg=args.start_phase,
        use_inverse_time=not args.no_inverse_time,
        z_min=args.z_min,
        z_max=args.z_max,
        precision=args.precision,
    )
    path = save_ngc(gcode, path=args.output, overwrite=args.overwrite)
    print(f"G-code saved to {path}")


if __name__ == "__main__":
    main()
