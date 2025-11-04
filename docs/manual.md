# APT Auto Electropolisher Manual

## Table of Contents

1. [System Overview](#system-overview)  
2. [Hardware Requirements](#hardware-requirements)  
3. [Software Installation](#software-installation)  
4. [Configuration Files](#configuration-files)  
   - [Hardware Settings (`config/settings.yml`)](#hardware-settings-configsettingsyml)  
   - [Polishing Defaults (`config/polishing.yml`)](#polishing-defaults-configpolishingyml)  
   - [Recipes (`recipes/*.yml`)](#recipes-recipesyml)  
5. [Motion Macros](#motion-macros)  
6. [Calibration Workflow](#calibration-workflow)  
   - [Slot & Camera Positions](#slot--camera-positions)  
   - [Thickness Calibration](#thickness-calibration)  
   - [Electrical Contact Detection](#electrical-contact-detection)  
7. [Graphical User Interface](#graphical-user-interface)  
   - [Launching](#launching)  
   - [Monitoring Pane](#monitoring-pane)  
   - [Manual Motion Pane](#manual-motion-pane)  
   - [Recipes Pane](#recipes-pane)  
   - [Setup Mode](#setup-mode)  
8. [Automation Workflow](#automation-workflow)  
   - [Pickup & Placement](#pickup--placement)  
   - [Beaker Contact](#beaker-contact)  
   - [Polishing Cycles](#polishing-cycles)  
   - [Imaging & Thickness Check](#imaging--thickness-check)  
   - [Cleaning & Storage](#cleaning--storage)  
9. [Command-Line Utilities](#command-line-utilities)  
10. [Testing & Development](#testing--development)  
11. [Safety Considerations](#safety-considerations)  
12. [Future Enhancements](#future-enhancements)

---

## System Overview

APT Auto Electropolisher automates specimen preparation for atom-probe tomography. The platform coordinates:

- A FluidNC-controlled gantry for specimen pickup, polishing, imaging, and storage.
- SCPI power supplies for voltage/current control.
- Cameras for microscopy and progress tracking.
- Sensors for current and temperature telemetry.
- Automated cleaning and drying stations.

The software is modular:

- `apt_polisher.motion`: G-code generation, macro streaming, FluidNC client.
- `apt_polisher.recipes`: Polishing recipe loader and motion macro metadata.
- `apt_polisher.orchestration`: High-level workflow (pickup → polish → inspect → finish).
- `apt_polisher.gui`: Qt-based monitoring GUI with manual controls and calibration tools.
- `apt_polisher.telemetry`: Time-series capture, plotting, CSV logging.

---

## Hardware Requirements

Minimum hardware to run the automation stack:

- **Gantry controller**: FluidNC/GRBL board with serial or network connectivity.
- **Power supply**: SCPI-compatible unit (LAN or serial interface).
- **Sensors**:
  - Current measurement (Hall sensor, shunt with ADC, or supply readback).
  - Temperature probe (thermocouple interface).
  - Inductive sensors for input/output buffer slots.
- **Cameras**: USB or CSI microscopes (microscope + overview recommended).
- **Cleaning system**: Nitrogen valve, solvent pumps, drying station.
- **Host machine**: Linux/macOS/Windows or Raspberry Pi running Python 3.10+ with PySide6.

---

## Software Installation

1. Clone the repository.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -e .[gui]
   ```
3. Run the test suite to verify installation:
   ```bash
   pytest
   ```

---

## Configuration Files

### Hardware Settings (`config/settings.yml`)

Stores machine-specific data:

- CNC serial port & baud rate.
- Power supply connection details (LAN or serial).
- Buffer slot coordinates (`buffers.input_slots`, `buffers.output_slots`).
- Camera positioning targets (`camera_positions.microscope_xyz`, etc.).
- Critical positions (`positions.beaker_xyz`, `positions.safe_z_mm`, `positions.polishing_zero_xyz`).
- Sensor identifiers.
- Calibration block for thickness scaling, contact approach parameters.
- File paths for image/telemetry storage.

The GUI’s setup mode can update coordinates and calibration values interactively.

### Polishing Defaults (`config/polishing.yml`)

Baseline waveform parameters (sine amplitude, period, duration), motion speeds, cleaning cycle defaults, etc. Recipes can override these values.

### Recipes (`recipes/*.yml`)

Each YAML recipe defines:

- Metadata (name, description).
- Motion macros (`motion_macros`) that point to G-code snippets (`recipes/motion/*.gcode`).
- Polishing parameters: safe Z, pickup/place macro names, waveform profile, contact detection thresholds, cycle mode (time/charge/count), voltage, current limit.
- Cleaning instructions (rinse/dry durations).
- Imaging thresholds (thickness limit, inspection interval).

Use `RecipeLoader` to enumerate and load recipes programmatically. When a specimen is loaded into an input slot, select the desired recipe (or accept the global default) via the GUI; that mapping is then used when the slot is enqueued for processing.

---

## Motion Macros

Macros are reusable G-code snippets stored under `recipes/motion/`. Examples:

- `pickup_standard.gcode`: Lower, latch, and retract a specimen from storage.
- `place_standard.gcode`: Insert specimen into storage slot.
- `cleaning_cycle.gcode`: Placeholder for rinse/dry station moves.

`MacroRunner` resolves macro paths relative to the recipes directory and streams commands through the FluidNC client.

---

## Calibration Workflow

### Slot & Camera Positions

Launch GUI with `--setup` to enable calibration controls. Jog the gantry, then press the desired slot/camera/beaker button to save the current position directly into `config/settings.yml`.

### Thickness Calibration

Use the “Calibrate Thickness” button in setup mode to launch a future calibration routine. Planned steps:
1. Place a wire with known diameter under the microscope.
2. Capture an image and measure pixel width.
3. Update `calibration.thickness` with reference microns, pixel count, and computed scale (`µm/pixel`).

### Electrical Contact Detection

Contact tuning values (`calibration.contact`) define approach step size, detection thresholds, and retract distance after sensing current flow. Adjust these empirically per electrolyte and geometry.

---

## Graphical User Interface

### Launching

```bash
python scripts/launch_gui.py            # Monitoring mode
python scripts/launch_gui.py --setup    # Adds calibration controls
```

### Monitoring Pane

- **Status**: Shows machine state, messages, and current reading.
- **G-code Pane**: Displays current program text.
- **Telemetry Plot**: Stacked chart (voltage/current + temperature) referencing live telemetry series.
- **Camera Pane**: Scrubbable feeds per camera with overlay toggle (analysis images).
- **Buffer Tables**: Occupancy status for input/output racks.

### Manual Motion Pane

Provides jog buttons and absolute move controls:

- Log-scale jog slider (0.01–10 mm) with synchronized spin box.
- Jog X/Y/Z ± buttons.
- Fields for absolute X/Y/Z moves (mm).
- Motion requests emit signals (`jog_requested`, `move_requested`) that upstream code should connect to the FluidNC client.

### Recipes Pane

- Global recipe dropdown.
- Per-slot recipe dropdowns for each input slot defined in the settings.
- Selection changes emit `global_recipe_selected` and `slot_recipe_selected` signals—wire them to the workflow queue to assign recipes before processing.
- Recommended workflow: choose the default global recipe (applies automatically when new specimens are detected) and override individual slots as needed when inserting specimens into the input rack. Record which slot holds which specimen so it can be enqueued with the corresponding recipe before starting automation.

### Setup Mode

Additional features when launched with `--setup`:

- Live gantry position display (from `MachineSnapshot.gantry_position`).
- Buttons to record coordinates for each slot, camera target, beaker, and polishing zero.
- Updates persist immediately into `config/settings.yml` (with confirmation dialogs).
- Thickness calibration launcher (placeholder for upcoming routine).

---

## Automation Workflow

The workflow orchestrates a specimen through these stages:

### Pickup & Placement

1. Move to safe Z (from recipe/settings).
2. Rapid to the input slot XY coordinates.
3. Execute the pickup macro: lower to engage the specimen, translate sideways to free it from the rack, then retract to the recipe’s safe Z height with the specimen captured.

### Beaker Contact

1. Rapid to beaker XY.
2. Apply the polishing voltage before descending so the first current spike identifies electrolyte contact.
3. Descend in relative mode using the calibrated approach step while monitoring current.
4. When current exceeds the detection threshold, record the depth, retract by the calibrated amount, and use that level as the polishing zero reference.

### Polishing Cycles

- Apply the recipe waveform (oscillatory motion about the detected zero) for the configured duration/cycle count (time-based initially; charge targets can be added later).
- Maintain voltage/current limits via SCPI power supply (future work hooks).
- Telemetry is logged continuously (CSV and plot).

### Imaging & Thickness Check

- After each polishing segment, move to the microscope position (using offsets so the active region is centered) and capture an image.
- Run image analysis (`apt_polisher.vision.analysis.detect_thinnest_section`) to measure minimum width in pixels, convert to microns via thickness calibration, and log the measurement.
- Continue polishing until thickness falls below the recipe-defined threshold before transitioning to finish steps.

### Cleaning & Storage

- After the target thickness is achieved, continue oscillating while monitoring current for a sharp drop (specimen separation indicator).
- Once detected, move the specimen to the cleaning station (macro) while maintaining safe Z clearances.
- Execute rinsing/drying sequences (solvent cycles and nitrogen blow) using recipe-defined durations.
- Transport to the selected output slot and run the placement macro (lower, side-release, retract), marking the slot occupied.

---

## Command-Line Utilities

- `scripts/generate_gcode.py`: Create stand-alone sine-wave G-code for manual testing.
- `scripts/autopolish.py`: Entry point for automation workflow (currently a scaffold; integrate queueing, recipes, vision, SCPI).
- `scripts/launch_gui.py`: Monitoring GUI (`--setup` enables calibration mode).
- Future utilities: calibration scripts, recipe validation, workflow testers.

---

## Testing & Development

- Run `pytest` to exercise unit tests (g-code generation, settings loaders, SCPI shim, telemetry, recipe parsing, workflow stubs).
- Extend `tests/` when adding new behaviour (e.g., contact detection algorithms, recipe schema changes, GUI signal wiring).
- Follow linting guidelines (`ruff` recommended) and keep docstrings concise.

---

## Safety Considerations

- Confirm safe Z heights before executing macros to avoid collisions.
- Use interlocks for acid bath, pumps, and nitrogen valves.
- Monitor current thresholds; excessive current indicates short circuits or rapid dissolution.
- Ensure emergency stop buttons and hardware limit switches are functional.
- Calibrate thickness measurement with verified standards before relying on automated thresholds.

---

## Future Enhancements

- **Full workflow implementation**: integrate SCPI supply control, vision feedback, and charge-based cycle termination.
- **Charge integration**: switch from duration-based cycles to total charge when desired.
- **Advanced imaging**: add multi-camera sequencing, autofocus, and focus stacking.
- **Persistent job queue**: track specimen state across restarts.
- **Calibration scripts**: automate thickness calibration, safe Z discovery, and contact characterization.
- **Data logging**: centralize per-specimen telemetry, image metadata, and recipe parameters for traceability.
