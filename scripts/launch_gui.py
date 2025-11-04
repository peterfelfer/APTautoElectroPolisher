#!/usr/bin/env python3
"""Launch the electropolisher GUI with mock data."""

from __future__ import annotations

import argparse
import itertools
from datetime import datetime
from pathlib import Path

from apt_polisher.gui.main_window import run_gui
from apt_polisher.gui.mock import generate_mock_snapshot
from apt_polisher.telemetry import TelemetryLogger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Enable setup mode controls to record slot/camera positions.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1500,
        help="Snapshot refresh interval in milliseconds (default: 1500).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counter = itertools.count()
    log_dir = Path("output/telemetry")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"mock_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    logger = TelemetryLogger(log_path)

    def provider():
        return generate_mock_snapshot(next(counter), logger=logger)

    try:
        run_gui(provider, snapshot_interval_ms=args.interval, enable_setup=args.setup)
    finally:
        logger.close()


if __name__ == "__main__":
    main()
