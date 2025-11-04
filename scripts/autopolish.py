#!/usr/bin/env python3
"""Entry point for executing an automated polishing run."""

from __future__ import annotations

import argparse
import sys

from apt_polisher.io import load_settings
from apt_polisher.motion import FluidNCClient, require_fluidnc_client
from apt_polisher.orchestration import PolishingWorkflow, WorkflowConfig
from apt_polisher.sensors import DummyCurrentSensor
from apt_polisher.instrumentation import SCPIPowerSupply


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Serial port connected to the FluidNC controller.")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate for the controller.")
    parser.add_argument("--storage-slot", type=int, default=0, help="Storage rack slot index to process.")
    parser.add_argument("--cycles", type=int, default=1, help="Number of polishing cycles to execute.")
    parser.add_argument("--settings", help="Optional path to a settings YAML file.")
    supply_group = parser.add_mutually_exclusive_group()
    supply_group.add_argument("--supply-host", help="Hostname/IP for the SCPI power supply (TCP).")
    supply_group.add_argument("--supply-serial", help="Serial port for the SCPI power supply (RS-232/USB).")
    parser.add_argument("--supply-port", type=int, default=5025, help="TCP port for the SCPI power supply (default 5025).")
    parser.add_argument("--supply-baud", type=int, default=9600, help="Baudrate for serial SCPI power supply (default 9600).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        require_fluidnc_client()
    except RuntimeError as exc:
        raise SystemExit(f"{exc}. Install the dependency or run inside hardware control environment.") from exc
    settings = load_settings(args.settings) if args.settings else load_settings()

    current_sensor = DummyCurrentSensor()
    workflow_config = WorkflowConfig(storage_slot=args.storage_slot, polishing_cycles=args.cycles)

    power_supply = None
    if args.supply_host:
        power_supply = SCPIPowerSupply.from_tcp(args.supply_host, port=args.supply_port)
    elif args.supply_serial:
        power_supply = SCPIPowerSupply.from_serial(args.supply_serial, baudrate=args.supply_baud)

    try:
        with FluidNCClient(args.port, baud=args.baud) as cnc:
            workflow = PolishingWorkflow(
                cnc=cnc,
                current_sensor=current_sensor,
                vision=None,
                power_supply=power_supply,
                config=workflow_config,
            )
            try:
                workflow.run()
            except NotImplementedError:
                print("Workflow execution is not yet implemented. Update 'PolishingWorkflow.run()' to proceed.")
                return 1
    finally:
        if power_supply:
            power_supply.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
