# garden_lab V2 Blueprint

This is the target architecture for the next `garden_lab` repo: a small platform with one registry, one data model, one API/web app/database core, and separate collection runtimes for local and remote sensors.

## Design Goals

- One core platform runtime
- One config-driven registry
- One standard model for sensors, actuators, automations, panels, and services
- One web app plus API plus database
- New hardware/features added mostly by config, not by app-specific route edits
- Sensor collection can run outside the core app and be managed independently

## Core Shift

V1 was centered on widgets and routes that knew about hardware.

V2 should be centered on:

- entities described in config
- drivers that implement standard interfaces inside the runtime where they belong
- services that operate on registered entities
- reusable UI panels driven by schemas/layout config

The site becomes a view over the registry, not the source of truth.

## Domain Model

Every configured thing belongs to one of a small number of types:

- `sensor`
- `actuator`
- `automation`
- `panel`
- `dashboard`
- `service`
- `collector`

Example entity set:

- `sensor.air_lab` produced by `collector.pi_zero_lab` using `i2c_sht40`
- `sensor.soil_tray_1` produced by `firmware.soil_probe_1` over `http_push`
- `actuator.exhaust_fan` using `tuya_outlet`
- `automation.fan_temp_control` watching `sensor.air_lab.temperature_c`
- `panel.air_lab_card` rendering `sensor_card`

## Runtime Layers

## 1. Core Platform

Responsibilities:

- load config
- validate config
- resolve env-backed secrets
- build the entity registry
- accept readings from collectors and remote firmware
- evaluate automations
- issue actuator commands
- serve dashboards and APIs
- persist data, events, and health

Suggested modules:

- `core/config/loader.py`
- `core/config/models.py`
- `core/config/registry.py`
- `core/services/ingestion.py`
- `core/services/automation.py`
- `core/services/commands.py`
- `core/services/health.py`

## 2. Collector Runtime

Responsibilities:

- run local hardware polling outside the core app
- host local sensor drivers
- normalize readings
- push readings and health into the core API

This is the home for local hardware integrations such as Pi-attached I2C sensors.

## 3. Remote Firmware Clients

Responsibilities:

- read remote hardware locally on-device
- normalize readings
- push readings into the core API
- remain tiny and operationally simple

Example:

- Pico W moisture probe firmware

## 4. Drivers

Responsibilities:

- integrate with hardware or external systems
- expose a fixed contract to the runtime that owns them

Driver placement matters:

- local sensor drivers live in the collector runtime
- remote firmware contains its own device-specific hardware logic
- actuator drivers usually live in core unless there is a strong reason to split them out

## 5. App

Responsibilities:

- serve dashboards
- expose generic entity-based APIs
- render reusable panels

## 6. Storage

Responsibilities:

- readings
- commands/events
- automation decisions
- latest health
- loaded config revisions

## Driver Contracts

## Collector Sensor Driver

```python
from typing import Protocol, Any

class SensorDriver(Protocol):
    def setup(self, config: dict[str, Any]) -> None: ...
    def read(self) -> dict[str, float | int | str | bool | None]: ...
    def health(self) -> dict[str, Any]: ...
```

Notes:

- `setup()` prepares bus/network/client state
- `read()` returns metric-name to value
- `health()` returns latest status metadata
- these drivers live in the collector runtime, not the core app

Initial collector sensor drivers:

- `i2c_sht40`

Future examples:

- `i2c_bme280`
- `serial_co2`

Remote sensors such as Pico devices are not collector drivers. They are separate firmware clients that post into the core API.

## Actuator Driver

```python
from typing import Protocol, Any

class ActuatorDriver(Protocol):
    def setup(self, config: dict[str, Any]) -> None: ...
    def get_state(self) -> dict[str, Any]: ...
    def apply(self, command: dict[str, Any]) -> dict[str, Any]: ...
    def health(self) -> dict[str, Any]: ...
```

Notes:

- core runtime code should not know Tuya or GPIO specifics
- it only sends commands like `{"power": true}`
- `apply()` returns a normalized result payload

Initial actuator drivers:

- `tuya_outlet`

Future examples:

- `gpio_relay`
- `smart_dimmer`
- `humidifier_switch`

## Config Model

Config should declare:

- app settings
- collectors
- driver registry
- sensors
- actuators
- automations
- dashboards
- services
- retention/storage policy

Suggested baseline:

```yaml
app:
  name: garden_lab
  timezone: America/New_York
  database_url: sqlite:///data/garden_lab.db
  ingest_base_url: http://gardenlab-core.local

collectors:
  pi_zero_lab:
    label: Lab Pi Zero
    enabled: true

drivers:
  collector_sensor:
    i2c_sht40: growlab.collector.drivers.sensor.i2c_sht40:SHT40Driver
  actuator:
    tuya_outlet: growlab.core.drivers.actuator.tuya_outlet:TuyaOutletDriver

sensors:
  air_lab:
    label: Seedling Air
    enabled: true
    source:
      kind: collector
      collector_id: pi_zero_lab
      driver: i2c_sht40
      poll:
        every_seconds: 60
      config:
        bus: 1
        address: 0x44
    metrics:
      temperature_c:
        label: Temperature
        unit: C
      humidity_pct:
        label: Humidity
        unit: "%"

  soil_tray_1:
    label: Soil Tray 1
    enabled: true
    source:
      kind: remote
      protocol: http_push
      auth_token: env:SOIL_TRAY_1_TOKEN
    metrics:
      moisture_pct:
        label: Moisture
        unit: "%"

actuators:
  exhaust_fan:
    label: Exhaust Fan
    driver: tuya_outlet
    enabled: true
    config:
      device_id: env:TUYA_FAN_DEVICE_ID
      ip: env:TUYA_FAN_IP
      local_key: env:TUYA_FAN_LOCAL_KEY
      version: 3.4
    commands:
      power:
        type: bool

automations:
  fan_temp_control:
    enabled: true
    mode: stateful
    logic:
      on:
        all:
          - sensor: air_lab
            metric: temperature_c
            op: ">="
            value: 28.0
            for_seconds: 180
      off:
        any:
          - sensor: air_lab
            metric: temperature_c
            op: "<="
            value: 25.5
            for_seconds: 180
    actions:
      on:
        - actuator: exhaust_fan
          command: { power: true }
      off:
        - actuator: exhaust_fan
          command: { power: false }
    cooldown_seconds: 120

dashboards:
  main:
    title: Seedling Lab
    layout:
      - panel: sensor_card
        entity: air_lab
      - panel: sensor_card
        entity: soil_tray_1
      - panel: actuator_card
        entity: exhaust_fan
      - panel: automation_card
        entity: fan_temp_control
```

## Config Rules

- Config declares entities and layout, not arbitrary HTML
- Secrets never live directly in committed config
- Panel types are fixed and reusable UI components
- Drivers are referenced by short names resolved through a registry
- Pydantic models should validate the full config tree before boot
- Sensors share one entity model even when their producers differ
- A sensor's `source` block determines whether it is produced by a collector or remote firmware

## Secret Handling

Use:

- `config/base.yaml`
- `config/local.yaml`
- `.env`

Pattern:

```yaml
config:
  local_key: env:TUYA_FAN_LOCAL_KEY
```

Rules:

- commit examples, not live secrets
- resolve `env:...` at config load time
- fail fast on missing required secrets

## Database Model

## `entities`

Registry snapshot of configured entities.

Columns:

- `entity_id`
- `entity_type`
- `label`
- `driver`
- `enabled`
- `config_json`
- `created_at_utc`
- `updated_at_utc`

## `sensor_readings`

Time-series sensor data.

Columns:

- `id`
- `sensor_id`
- `ts_utc`
- `metric`
- `value_num`
- `value_text`
- `quality`
- `source_kind`
- `source_id`

Notes:

- use `value_num` for numeric metrics
- keep `value_text` for string or status-style metrics
- `source_kind` distinguishes `collector`, `remote`, or `backfill`
- `source_id` identifies the producer, such as `pi_zero_lab` or `soil_tray_1`

## `collector_events`

Collector heartbeats and operational events.

Columns:

- `id`
- `collector_id`
- `ts_utc`
- `event_type`
- `payload_json`
- `status`

## `actuator_events`

Command attempts and observed state changes.

Columns:

- `id`
- `actuator_id`
- `ts_utc`
- `event_type`
- `payload_json`
- `status`

`event_type` examples:

- `command`
- `state_change`
- `error`

## `automation_events`

Automation evaluations and resulting actions.

Columns:

- `id`
- `automation_id`
- `ts_utc`
- `decision`
- `reason`
- `payload_json`

## `entity_health`

Latest health snapshot per entity.

Columns:

- `entity_id`
- `ts_utc`
- `status`
- `message`
- `payload_json`

## `config_revisions`

Loaded config history.

Columns:

- `revision_id`
- `loaded_at_utc`
- `config_yaml`
- `hash`

## API Shape

The API should be generic and entity-based.

Suggested endpoints:

- `GET /api/entities`
- `GET /api/sensors/{sensor_id}/latest`
- `GET /api/sensors/{sensor_id}/history?metric=temperature_c&hours=24`
- `POST /api/ingest/sensors/{sensor_id}`
- `POST /api/collectors/{collector_id}/heartbeat`
- `GET /api/actuators/{actuator_id}/state`
- `POST /api/actuators/{actuator_id}/commands`
- `GET /api/automations/{automation_id}`
- `POST /api/automations/{automation_id}/enable`
- `POST /api/automations/{automation_id}/disable`
- `GET /api/health`
- `GET /api/dashboards/{dashboard_id}`

Rules:

- no per-widget custom endpoints
- stable schemas via Pydantic
- producer ingestion authenticated
- timestamps normalized to UTC in storage

## Dashboard Model

The frontend should be config-driven within a clear boundary.

Config should define:

- dashboards/pages
- panel order/layout
- entity binding
- visible metrics
- chart ranges
- grouping/sections

Config should not define:

- arbitrary HTML
- bespoke JS behavior
- one-off hardware-specific rendering code

## Initial Panel Types

- `sensor_card`
- `sensor_chart`
- `sensor_table`
- `actuator_card`
- `automation_card`
- `health_card`
- `notes_card`

Each panel type is implemented once and reused everywhere through config.

## Services

## Config Loader

Responsibilities:

- read base and local config
- resolve env values
- validate into typed models
- publish loaded config revision

## Driver Registry

Responsibilities:

- resolve configured driver names to classes
- instantiate drivers
- manage driver setup lifecycle

Note:

- core resolves actuator drivers
- collector resolves local sensor drivers

## Ingestion Service

Responsibilities:

- validate collector and remote firmware payloads
- authenticate producer
- persist readings
- update health

## Command Service

Responsibilities:

- validate command schema for an actuator
- call driver `apply()`
- record command result and state

## Automation Service

Responsibilities:

- evaluate logic against recent state
- support hysteresis and cooldowns
- emit automation events
- dispatch actuator commands

## Health Service

Responsibilities:

- compute and store latest health for each entity
- expose runtime readiness and dependency errors

## Collector Service

Responsibilities:

- schedule local sensor polls
- run collector sensor drivers
- normalize readings
- POST readings to core ingestion endpoints
- POST collector heartbeat and health to core

## Remote Firmware Contract

Responsibilities:

- read device-local hardware
- normalize readings to the shared platform schema
- authenticate to the core ingestion endpoint
- retry safely and sleep efficiently

## Automation Semantics

V2 automations should support:

- threshold comparisons
- `for_seconds`
- hysteresis
- cooldowns
- time windows
- multiple conditions
- explicit `on` and `off` logic
- safety fallback behavior

Recommended implementation model:

- stateful automations
- separate `on` and `off` condition trees
- command deduping so the runtime does not spam identical commands every cycle

## Suggested Stack

Best-fit stack for this project:

- FastAPI for core
- Jinja templates
- HTMX
- Alpine.js
- SQLAlchemy or SQLModel
- SQLite
- APScheduler
- Pydantic

Collector runtime:

- Python
- same shared config schema where practical
- APScheduler or a simple worker loop

Remote firmware:

- MicroPython on Pico W

Reasoning:

- keeps core focused on platform concerns
- keeps hardware polling outside the web app
- supports both Pi-attached and remote sensors cleanly
- still remains lightweight enough for the garden lab

## Repo Layout

```text
garden_lab/
  pyproject.toml
  README.md
  .env.example

  config/
    base.yaml
    local.example.yaml

  data/
    .gitkeep

  migrations/

  src/growlab/
    core/
      app/
        main.py
        routes_dashboard.py
        routes_api.py
        dependencies.py

      config/
        loader.py
        models.py
        registry.py

      db/
        models.py
        session.py
        repo_readings.py
        repo_events.py

      drivers/
        actuator/
          base.py
          tuya_outlet.py
          gpio_relay.py

      services/
        ingestion.py
        automation.py
        commands.py
        health.py

      panels/
        sensor_card.py
        actuator_card.py
        automation_card.py

      templates/
        base.html
        dashboard.html
        panels/

      static/
        css/
        js/

      schemas/
        api.py
        config.py

    collector/
      app.py
      heartbeat.py
      ingestion_client.py
      drivers/
        sensor/
          base.py
          i2c_sht40.py
          i2c_bme280.py
      services/
        polling.py
        health.py

    shared/
      time.py
      ids.py
      signing.py

  firmware/
    pico_moisture/
      main.py
      boot.py
      README.md

  scripts/
    dev_core.py
    dev_collector.py
    init_db.py
```

## Build Phases

## Phase 1: Solid Core

Build first:

- config loader
- typed config schema
- entity registry
- DB models and migrations
- ingestion service
- collector runtime
- first collector sensor driver
- first remote firmware contract
- actuator command service
- generic history and state API
- basic dashboard with reusable panels

Do not build first:

- elaborate automation UI
- alerts
- auth-heavy admin system

## Phase 2: Automations

Add:

- stateful rule engine
- hysteresis
- cooldowns
- automation event log
- enable and disable controls
- automation panel and diagnostics

## Phase 3: Polish

Add:

- stronger authenticated remote ingestion
- health and status dashboards
- alerts
- Pi service packaging
- export and backup
- retention policies

## Acceptance Test For The Architecture

The real design test is whether adding hardware avoids core app edits.

Examples:

Add a new BME280 sensor:

1. add `collector/drivers/sensor/i2c_bme280.py`
2. register the collector driver
3. add a sensor entry in YAML with a collector source
4. add a panel entry

Add another Tuya outlet:

1. reuse `tuya_outlet`
2. add an actuator config entry
3. add a panel entry
4. optionally add automation config

No app-specific route additions. No hardware-specific dashboard logic.

## Immediate Recommendation

Use this blueprint as the design target, then implement the new repo in this order:

1. config schema and registry
2. DB schema and repositories
3. core ingestion and command interfaces
4. collector runtime plus SHT40 driver
5. actuator driver interfaces plus Tuya implementation
6. generic API
7. reusable dashboard panels
8. automation engine
