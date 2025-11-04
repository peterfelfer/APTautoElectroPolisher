#!/usr/bin/env python3
"""Quick helper to run the specimen thinning detector on an image."""

from __future__ import annotations

import argparse
from pathlib import Path

from apt_polisher.vision import detect_thinnest_section


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to the microscope image to analyse.")
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display diagnostic plots (requires GUI backend).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.image.exists():
        raise SystemExit(f"Image not found: {args.image}")
    result = detect_thinnest_section(str(args.image), show_plots=args.show)
    print(f"Minimum width: {result['minWidthPx']:.2f} px at row {result['rowIdx']}")


if __name__ == "__main__":
    main()
