# APTautoElectroPolisher

Automated electropolishing platform for atom-probe specimens. The system coordinates a FluidNC-driven gantry, polishing vats, cleaning stations, imaging, and current sensing to prepare tips repeatably.

## Repository Layout

- `apt_polisher/` – Python package with reusable modules
  - `motion/` – FluidNC client and G-code generation utilities
  - `vision/` – Image-analysis helpers for monitoring thinning progress
  - `sensors/` – Interfaces for current and environmental sensors
  - `instrumentation/` – SCPI and hardware control helpers (power supplies, meters)
  - `io/` – Configuration loading and persistence utilities
  - `orchestration/` – High-level workflow primitives
- `recipes/` – YAML electropolishing recipes and motion macros (`recipes/motion/*.gcode`)
- `scripts/` – Command-line entry points (automated runs, G-code generation, camera calibration)
- `config/` – Project configuration files (e.g., `settings.yml`, `polishing.yml`)
- `data/` – Raw and processed datasets (gitignored for large files)
- `output/` – Generated artifacts such as G-code (gitignored)
- `docs/` – Engineering notes and architecture documentation
- `docs/manual.md` – Comprehensive operator and developer documentation
- `tests/` – Pytest-based unit tests

## Quick Start

1. Create a virtual environment and install dependencies: `pip install -e .`
2. Adjust `config/settings.yml` for your hardware layout.
3. Generate a polishing waveform: `python scripts/generate_gcode.py --center 10 --amplitude 0.5 --period 2 --cycles 5`
4. Connect to the FluidNC controller and run (workflow implementation pending): `python scripts/autopolish.py --port /dev/ttyUSB0`
5. Launch the monitoring GUI with mock data (requires `pip install .[gui]`): `python scripts/launch_gui.py` — add `--setup` to expose the calibration controls. Scrub through camera frames, toggle the analysis overlay, manage global/per-slot recipe selections, explore manual jog/absolute moves, tag slot/camera positions in setup mode, and watch live telemetry charts for voltage/current/temperature (logged under `output/telemetry/`).
6. Define electropolishing recipes under `recipes/*.yml` (motion macros in `recipes/motion/`) and connect a SCPI power supply during automation runs via TCP (`--supply-host 192.168.1.50 --supply-port 5025`) or serial (`--supply-serial COM5 --supply-baud 9600`). Consult `docs/manual.md` for full setup, calibration, and workflow details.

## Development

- Run unit tests with `pytest`.
- Lint using `ruff` or `flake8` (add to `pyproject.toml` as needed).
- See `docs/overview.md` for a subsystem breakdown and roadmap notes.
