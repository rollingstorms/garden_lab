# GrowLab

GrowLab is split into three layers:

- `core`: API, dashboard, database, automations, and actuator commands
- `collector`: local sensor polling runtime for Pi-attached hardware
- `firmware`: tiny remote clients such as Pico-based probes

## Layout

- `config/base.yaml`: shared config
- `config/local.example.yaml`: local override example
- `src/growlab/core`: core platform code
- `src/growlab/collector`: collector runtime
- `firmware/pico_moisture`: Pico moisture probe placeholder

## Quick Start

1. Create a virtualenv and install with `pip install -e .`
2. Copy `.env.example` to `.env`
3. Copy `config/local.example.yaml` to `config/local.yaml`
4. Start the core app with `python scripts/dev_core.py`

This scaffold is intentionally thin. It establishes the package boundaries and typed config model first.
