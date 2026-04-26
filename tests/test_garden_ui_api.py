from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from growlab.core.app.dependencies import get_session_factory, reset_runtime_caches
from growlab.core.app.main import create_app
from growlab.core.db.repo_events import insert_actuator_event
from growlab.core.db.repo_overrides import list_manual_overrides
from growlab.shared.time import utc_now


def build_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    db_path = tmp_path / "garden.db"
    local_path = tmp_path / "local.yaml"
    local_path.write_text(
        yaml.safe_dump({"app": {"database_url": f"sqlite:///{db_path}"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("GROWLAB_CONFIG_BASE", str(Path("config/base.yaml").resolve()))
    monkeypatch.setenv("GROWLAB_CONFIG_LOCAL", str(local_path.resolve()))
    reset_runtime_caches()

    def fake_issue_command(self, *, registry, session, actuator_id, payload):
        result = {
            "accepted": True,
            "actuator_id": actuator_id,
            "driver": registry.get_actuator(actuator_id).driver,
            "command": payload.command,
            "state": {"power": payload.command.get("power")},
        }
        insert_actuator_event(
            session,
            actuator_id=actuator_id,
            ts_utc=utc_now(),
            event_type="command",
            status="accepted",
            payload=result,
        )
        return result

    monkeypatch.setattr(
        "growlab.core.services.commands.CommandService.issue_command",
        fake_issue_command,
    )
    client = TestClient(create_app())
    return client, local_path


def seed_air_sensor(client: TestClient, *, temp: float, humidity: float) -> None:
    response = client.post(
        "/api/ingest/sensors/air_lab",
        json={
            "ts_utc": utc_now().isoformat(),
            "metrics": {
                "temperature_c": temp,
                "humidity_pct": humidity,
            },
        },
    )
    assert response.status_code == 200


def test_manual_override_expiry_returns_device_to_auto(tmp_path: Path, monkeypatch) -> None:
    client, _ = build_client(tmp_path, monkeypatch)
    seed_air_sensor(client, temp=20.0, humidity=50.0)

    response = client.post(
        "/api/overrides/actuators/exhaust_fan",
        json={"mode": "on", "reason": "test_override"},
    )
    assert response.status_code == 200

    response = client.post("/api/automations/run")
    assert response.status_code == 200
    assert response.json()["garden"]["actuators"]["exhaust_fan"]["power"] is True

    session = get_session_factory()()
    try:
        override = list_manual_overrides(session, actuator_id="exhaust_fan", status="active", limit=1)[0]
        override.expires_at_utc = utc_now() - timedelta(seconds=1)
        session.add(override)
        session.commit()
    finally:
        session.close()

    response = client.post("/api/automations/run")
    assert response.status_code == 200

    response = client.get("/api/garden/state")
    assert response.status_code == 200
    garden = response.json()
    assert garden["actuators"]["exhaust_fan"]["override"] is None
    assert garden["actuators"]["exhaust_fan"]["power"] is False


def test_emergency_overrides_manual_on(tmp_path: Path, monkeypatch) -> None:
    client, _ = build_client(tmp_path, monkeypatch)
    seed_air_sensor(client, temp=35.0, humidity=50.0)

    response = client.post(
        "/api/overrides/actuators/warm_pads",
        json={"mode": "on", "reason": "manual_test"},
    )
    assert response.status_code == 200

    response = client.post("/api/automations/run")
    assert response.status_code == 200
    payload = response.json()["garden"]
    assert payload["decision"]["reason"] == "garden_emergency"
    assert payload["actuators"]["warm_pads"]["power"] is False
    assert payload["actuators"]["exhaust_fan"]["power"] is True


def test_invalid_config_patch_rejected(tmp_path: Path, monkeypatch) -> None:
    client, _ = build_client(tmp_path, monkeypatch)

    response = client.patch(
        "/api/config/garden/climate",
        json={
            "mode": "simple",
            "temperature_on_above": 20.0,
            "temperature_off_below": 25.0,
            "humidity_on_above": 75.0,
            "humidity_off_below": 60.0,
            "heat_on_below": 19.0,
            "heat_off_above": 21.0,
        },
    )
    assert response.status_code == 422


def test_config_patch_updates_local_override_and_reload(tmp_path: Path, monkeypatch) -> None:
    client, local_path = build_client(tmp_path, monkeypatch)

    response = client.patch(
        "/api/config/garden/watering",
        json={
            "mode": "simple",
            "watering_mode": "schedule",
            "interval_minutes": 180,
            "run_seconds": 45,
            "anchor": "07:30",
        },
    )
    assert response.status_code == 200

    local_data = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    assert local_data["automations"]["garden_equilibrium"]["controller"]["watering"]["schedule"]["interval_minutes"] == 180

    response = client.get("/api/garden/config")
    assert response.status_code == 200
    assert response.json()["effective"]["watering"]["schedule"]["interval_minutes"] == 180


def test_return_to_auto_clears_all_overrides(tmp_path: Path, monkeypatch) -> None:
    client, _ = build_client(tmp_path, monkeypatch)
    client.post("/api/overrides/actuators/exhaust_fan", json={"mode": "on"})
    client.post("/api/overrides/actuators/lamps", json={"mode": "off"})

    response = client.post("/api/garden/return-to-auto")
    assert response.status_code == 200
    assert sorted(response.json()["cancelled"]) == ["exhaust_fan", "lamps"]

    response = client.get("/api/garden/state")
    assert response.status_code == 200
    assert response.json()["actuators"]["exhaust_fan"]["override"] is None
    assert response.json()["actuators"]["lamps"]["override"] is None


def test_module_enabled_toggle_persists_and_disables_commands(tmp_path: Path, monkeypatch) -> None:
    client, local_path = build_client(tmp_path, monkeypatch)

    response = client.patch("/api/config/garden/light/enabled", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["effective"]["enabled"] is False

    local_data = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    assert local_data["automations"]["garden_equilibrium"]["controller"]["light"]["enabled"] is False

    response = client.post("/api/automations/run")
    assert response.status_code == 200

    response = client.get("/api/garden/config")
    assert response.status_code == 200
    assert response.json()["effective"]["light"]["enabled"] is False

    response = client.get("/api/garden/state")
    assert response.status_code == 200
    assert response.json()["actuators"]["lamps"]["power"] is None


def test_reset_config_restores_base_defaults(tmp_path: Path, monkeypatch) -> None:
    client, local_path = build_client(tmp_path, monkeypatch)
    base_data = yaml.safe_load(Path("config/base.yaml").read_text(encoding="utf-8"))
    base_interval = (
        base_data["automations"]["garden_equilibrium"]["controller"]["watering"]["schedule"]["interval_minutes"]
    )

    response = client.patch(
        "/api/config/garden/watering",
        json={
            "mode": "simple",
            "watering_mode": "schedule",
            "interval_minutes": 180,
            "run_seconds": 45,
            "anchor": "07:30",
        },
    )
    assert response.status_code == 200

    response = client.post("/api/config/garden/reset")
    assert response.status_code == 200
    assert response.json()["effective"]["watering"]["schedule"]["interval_minutes"] == base_interval

    local_data = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
    controller = (
        local_data.get("automations", {})
        .get("garden_equilibrium", {})
        .get("controller")
    )
    assert controller is None

    response = client.get("/api/garden/config")
    assert response.status_code == 200
    assert response.json()["effective"]["watering"]["schedule"]["interval_minutes"] == base_interval
