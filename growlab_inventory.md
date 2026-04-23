# GrowLab Monitor Inventory

This document inventories what `/Users/michaelroth/Documents/Code/weather_station/growlab` currently does, based on the local codebase at `main` and its checked-in config/artifacts.

## Purpose

The project is a Raspberry Pi-hosted Flask dashboard for a small grow environment. It combines:

- Local sensor polling over I2C
- Remote sensor ingestion over HTTP
- SQLite storage for readings and device state changes
- A browser dashboard with per-device widgets
- Local-network control of at least one Tuya smart plug
- A first pass at rule-based automation

## Runtime Architecture

## Backend

- Python Flask app in `app.py`
- APScheduler background job for periodic sensor polling
- SQLite database file configured as `data.db`
- Dynamic widget loading from `config.yaml`

## Frontend

- Server-rendered Jinja templates
- Per-widget JavaScript loaded from `static/js/widgets`
- Chart.js charts rendered in the browser
- Shared widget styling in `static/css/widgets.css`

## Configuration

The app is driven primarily by `config.yaml`.

It defines:

- Database path
- Dashboard title
- Widget classes/modules
- Devices shown on the dashboard
- Sensor definitions and metric labels
- Automation control defaults
- Polling interval
- Some older threshold/plug config that is not actively used by the current Tuya path

## Implemented Features

## 1. Dashboard UI

The root route `/` renders a dashboard containing one widget per configured device/control entry.

Current configured widgets:

- `sensor1`: local air sensor
- `pico_soil`: remote soil sensor
- `fan1`: Tuya-controlled exhaust fan
- `temp_fan_control`: automation control widget

Each widget is clickable and links to `/widget/<device_id>` for a detail view.

## 2. Dynamic Widget System

Widgets are instantiated dynamically from `config.yaml` using module/class names.

Implemented widget types:

- `SensorWidget`
- `DeviceWidget`
- `ClockWidget`
- `ControlWidget`

The current config does not enable the clock widget, but the class and client code exist.

## 3. Local Sensor Polling

The app schedules `store_reading()` on a fixed interval from `config.yaml`.

Current interval:

- Every 60 seconds

Current local polling behavior:

- Scans configured devices where `type: sensor` and `source: local`
- Reads the sensor over I2C bus 1
- Supports sensor-type dispatch, though only `SHT40` is implemented
- Converts raw SHT40 bytes into:
  - `temperature_C`
  - `humidity_pct`
- Stores readings in SQLite as one row per `(device_id, timestamp, metric)`

## 4. Remote Sensor Ingestion

The app exposes a generic POST ingestion API:

- `POST /api/ingest`

Expected payload shape:

- `device_id`
- `ts` as Unix timestamp
- Any additional keys are treated as metrics

This supports remote devices such as the configured `pico_soil` sensor.

## 5. Sensor History API

Implemented reading endpoints:

- `GET /api/<device_id>/sensor_data`
- `GET /api/readings?device_id=<id>`
- `GET /api/diagnostic/readings`

Behavior:

- `SensorWidget` returns current values plus recent history for charting
- History is limited to the last 24 hours and then sampled down for display
- The generic `/api/readings` endpoint returns the latest 100 reading rows for one device
- The diagnostic endpoint returns raw rows for debugging, optionally filtered by device

## 6. Sensor Widget UI

The sensor widget renders:

- Current value display for each configured metric
- One Chart.js line chart per metric
- A readings table with timestamps and metric values

Frontend behavior:

- Polls `/api/<device_id>/sensor_data` every 60 seconds
- Handles no-data states explicitly
- Samples history for chart readability

## 7. Device Control

The device widget exposes:

- `GET /api/<device_id>/status`
- `POST /api/<device_id>/control`

Current implemented control path:

- If `device_type: tuya`, control is performed with `tinytuya.OutletDevice`
- Uses device metadata from `config.yaml`:
  - `dev_id`
  - `ip`
  - `local_key`
  - `version`
- Successful on/off actions are logged to `device_logs` in SQLite

The current configured controlled device is:

- `fan1` / "Exhaust Fan"

## 8. Device State Logging

Every successful device on/off action is logged into a `device_logs` table with:

- Timestamp
- Device ID
- State

The status/history API reads from this table to drive the device widget.

## 9. Automation Control Widget

A control widget exists for rule-based automation and is configured as:

- `temp_fan_control`

Its intended rule is:

- Monitor `sensor1`
- Watch metric `temperature_C`
- Turn `fan1` on when the value is `>` `28.0`

Implemented backend pieces:

- `GET /api/<control_id>/config`
- `POST /api/<control_id>/config`
- `POST /api/<control_id>/manual`
- Background control loop thread per control widget
- SQLite-backed `control_configs` table
- Periodic evaluation of one configured comparison rule

Current control loop behavior:

- Loads control config from DB or seeds it from `config.yaml`
- Reads latest sensor value
- Compares against threshold using one operator
- Calls device control every 60 seconds based on the result

Supported operators:

- `>`
- `>=`
- `<`
- `<=`
- `=`

## 10. Clock API and Widget

Implemented but not currently configured on the dashboard:

- `GET /api/clock`
- `ClockWidget`
- Browser polling every second to show server time

## 11. Tuya Discovery and Metadata Artifacts

The repo includes local/network integration artifacts:

- `devices.json`: Tuya device metadata and DPS mapping
- `snapshot.json`: network discovery snapshot with live-ish device state
- `tinytuya.json`: Tuya Cloud API credentials/config
- `tuya-raw.json`: raw Tuya output artifact
- `tinytuya_example.py`: ad hoc local control example

These are operational/support files rather than core app code, but they show the system depends on local-network Tuya access and discovery.

## Data Model

## `readings`

Primary time-series table for sensor data.

Columns:

- `device_id`
- `ts`
- `metric`
- `value`

Primary key:

- `(device_id, ts, metric)`

## `device_logs`

Event log for controlled device state changes.

Columns:

- `ts`
- `device_id`
- `state`

## `control_configs`

Persisted automation rule config.

Columns:

- `control_id`
- `sensor_id`
- `device_id`
- `metric`
- `operator`
- `target_value`
- `enabled`

## Current Configured Physical / Logical Entities

## Sensors

- `sensor1`: local SHT40 air sensor on I2C address `0x44`
- `pico_soil`: remote soil moisture sensor expected to report through `/api/ingest`

## Controlled Device

- `fan1`: Tuya smart plug at local IP `192.168.68.150`

## Automation

- `temp_fan_control`: threshold-based fan automation tied to `sensor1.temperature_C`

## Gaps, Dead Code, and Half-Wired Features

These are important because they affect what should be carried into a new repo versus what should be redesigned.

## 1. Legacy controller module is mostly inactive

`controller.py` still contains an older generic plug-control path, but the actual plug integration is commented out. The live device control path is in `widgets/device.py` via `tinytuya`.

## 2. Imported aliases are unused

`app.py` imports `set_fan` and `set_light`, but does not use them.

## 3. Some frontend code references missing APIs

`static/js/widgets/control.js` calls endpoints that do not exist in the Flask app:

- `/api/sensors`
- `/api/automation/rules`
- `/api/automation/check`

That means part of the automation UI is aspirational rather than functional.

## 4. Widget registry is expected but never attached

`ControlWidget` looks up `app.config["_widgets"]` to discover sensors/devices and dispatch control through widget instances, but `app.py` never stores the instantiated widget list there.

Effect:

- Sensor/device dropdown population in the control widget can be empty
- Control dispatch falls back to `controller.set_device()`
- That fallback will fail for non-Tuya generic devices because the old plug path is stubbed

## 5. Device template and `device.js` do not match

`static/js/widgets/device.js` expects DOM elements:

- `.device-toggle`
- `.toggle-label`

But the device template only renders on/off buttons. A different script, `control.js`, replaces the device buttons with a toggle and ends up acting as the real device-widget controller.

So there are overlapping frontend implementations for device control.

## 6. Clock widget exists but is not configured

The code exists, but `config.yaml` does not define a clock device/widget entry to render it.

## 7. Timestamp handling is inconsistent

Different paths use:

- `datetime.now().isoformat()`
- `datetime.utcnow().isoformat()`
- `datetime.utcfromtimestamp(ts).isoformat()`
- SQLite `datetime('now', '-24 hours')`

A rebuild should normalize timestamps and timezone policy.

## 8. Secrets are stored in repo-local files

The repository currently contains:

- Tuya local keys
- Tuya cloud API keys/secrets
- Device IPs and IDs

These should not be carried forward into a new public repo layout.

## 9. Remote sensor ingestion has no auth/validation layer

`/api/ingest` accepts arbitrary JSON metrics once `device_id` and `ts` are present.

That is fine for prototyping on a trusted LAN, but weak for a cleaner production design.

## 10. No explicit process/service packaging

The code runs as a Flask app plus background threads/scheduler, but there is no visible systemd/service/deployment scaffolding in this repo snapshot.

## What The System Actually Does Today

If this repo is running on the nearby Raspberry Pi, the likely active behavior is:

1. Serve a web dashboard on port `5000`
2. Poll the local SHT40 every minute
3. Store temperature and humidity in SQLite
4. Accept remote sensor submissions for things like soil moisture
5. Render sensor charts/tables in the browser
6. Control the Tuya exhaust fan over the local network
7. Log fan on/off events
8. Run a threshold loop that can turn the fan on when temperature exceeds the configured setpoint

## Likely Intent For A Clean Rebuild

The repo suggests the new system should probably preserve these product-level capabilities:

- Unified grow-room dashboard
- Local and remote sensor support
- Historical data storage
- Smart plug/device control
- Rule-based automation
- Extensible widget or panel system
- Raspberry Pi-friendly local deployment

But it should probably rebuild these parts cleanly:

- Device and automation APIs
- Widget/data registry
- Config and secrets handling
- Timestamp and schema consistency
- Frontend control layer
- Deployment/service setup

## Source Files Reviewed

Primary files reviewed for this inventory:

- `/Users/michaelroth/Documents/Code/weather_station/growlab/app.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/config.yaml`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/controller.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/sensor.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/sht40.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/widgets/base_widget.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/widgets/sensor.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/widgets/device.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/widgets/control_widget.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/widgets/clock.py`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/templates/base.html`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/templates/widget_detail.html`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/templates/widgets/sensor.html`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/templates/widgets/device.html`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/templates/widgets/control.html`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/templates/widgets/clock.html`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/static/js/widgets/sensor.js`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/static/js/widgets/device.js`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/static/js/widgets/control.js`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/static/js/widgets/clock.js`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/static/css/widgets.css`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/devices.json`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/snapshot.json`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/tinytuya.json`
- `/Users/michaelroth/Documents/Code/weather_station/growlab/tinytuya_example.py`
