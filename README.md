# garden_lab

`garden_lab` is split into three layers:

- `core`: API, dashboard, database, automations, and actuator commands
- `collector`: local sensor polling runtime for Pi-attached hardware
- `firmware`: tiny remote clients such as Pico-based probes

## Layout

- `config/base.yaml`: shared config
- `config/local.example.yaml`: local override example
- `.env.example`: local environment variables and secrets template
- `src/growlab/core`: core platform code
- `src/growlab/collector`: collector runtime
- `firmware/pico_moisture`: Pico moisture probe placeholder

## Quick Start

1. Create a virtualenv and install with `pip install -e .`
2. Copy `.env.example` to `.env`
3. Copy `config/local.example.yaml` to `config/local.yaml`
4. Initialize the database with `python scripts/init_db.py`
5. Start the core app with `python scripts/dev_core.py`
6. Start the collector with `python scripts/dev_collector.py`

The core app serves the dashboard and API, runs the automation loop, and records commands and events. The collector runs as a separate long-lived process that polls Pi-attached sensors and posts normalized readings back to core.

## Pi Deploy

1. Clone the repo onto the Pi at `/home/pi/garden_lab`
2. Run `bash scripts/bootstrap_pi.sh`
3. Fill in `.env` and `config/local.yaml`
4. Set `GARDEN_LAB_HOST=0.0.0.0` in `.env` if you want LAN access
5. Install the service files from `deploy/systemd/`
6. Enable `garden-lab-core` and `garden-lab-collector`
