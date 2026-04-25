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

## Main Garden Algorithm

The default control loop now treats the lab like a small equilibrium system instead of a single threshold toggle.

- `garden_equilibrium` is the main automation in `config/base.yaml`
- climate control is modular: fan cooling and pad heating each use their own hysteresis bands
- lamps run on a daily schedule
- watering can run either on a timed pulse schedule or from a soil-moisture threshold
- emergency logic overrides everything else and forces the safe state: fan on, lamps off, pads off

If you want to switch watering from timed to sensor-driven control, keep the same `watering.actuator` and change `watering.mode` from `schedule` to `sensor`, then provide the soil sensor and thresholds under `watering.sensor`.

## Kauf Smart Plugs

The default actuator setup now expects four Kauf plugs reachable on the LAN through the ESPHome native API:

- `exhaust_fan`
- `water_pump`
- `warm_pads`
- `lamps`

Set `KAUF_FAN_HOST`, `KAUF_PUMP_HOST`, `KAUF_PADS_HOST`, and `KAUF_LAMPS_HOST` in `.env` to the plugs' hostnames or IPs. If your Tasmota setup uses HTTP auth or non-default relay naming, add those overrides in `config/local.yaml` under each actuator's `config`.
The Kauf plugs currently advertising on the LAN expose the primary relay as ESPHome switch object id `kauf_plug`, which is the default actuator target in `config/base.yaml`.
Discovered hostnames on the current LAN are `kauf-plug-f1e4e6.local`, `kauf-plug-f1d123.local`, `kauf-plug-f1d12a.local`, and `kauf-plug-f1d1f5.local`; map those to fan/pump/pads/lamps however you physically assign them.

## Pi Deploy

1. Clone the repo onto the Pi at `/home/pi/garden_lab`
2. Run `bash scripts/bootstrap_pi.sh`
3. Fill in `.env` and `config/local.yaml`
4. Set `GARDEN_LAB_HOST=0.0.0.0` in `.env` if you want LAN access
5. Install the service files from `deploy/systemd/`
6. Enable `garden-lab-core` and `garden-lab-collector`
