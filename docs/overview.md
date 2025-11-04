# System Overview

The automated electropolisher coordinates three main subsystems:

1. **Motion Control** – A FluidNC-controlled gantry moves specimens between storage, polishing, and cleaning stations. See `apt_polisher/motion/`.
2. **Vision** – Cameras capture snapshots for monitoring thinning progress and documenting runs. Image processing lives in `apt_polisher/vision/`.
3. **Sensing** – Current and environmental sensors provide real-time feedback for end-point detection. Interfaces are defined in `apt_polisher/sensors/`.

High-level workflows that sequence these subsystems reside in `apt_polisher/orchestration/`.

The operator-facing GUI (`apt_polisher/gui/`) visualises buffer sensors, active G-code, current/voltage/temperature telemetry (with rolling plots), jog/absolute motion controls, setup helpers for recording slot/camera coordinates, and camera feeds (scrubbing plus analysis overlays) so that polishing progress can be monitored live. Telemetry is streamed to CSV via `apt_polisher/telemetry/`, while SCPI-capable instruments (e.g., polishing power supplies) are managed through `apt_polisher/instrumentation/`.

Supporting assets such as configuration files belong under `config/` (`settings.yml` for hardware, `polishing.yml` for process recipes), experimental datasets under `data/`, and generated artifacts (e.g., G-code) under `output/`.

Polishing behaviour is controlled by YAML recipes in `recipes/`, each of which references motion macros (G-code snippets) in `recipes/motion/`. Calibration data (slot coordinates, microscope offsets, thickness scaling) is stored in `config/settings.yml` and can be updated through the GUI’s setup mode.
