const state = {
  garden: null,
  configModes: {
    "climate-config": "simple",
    "light-config": "simple",
    "watering-config": "simple",
    "emergency-config": "simple",
  },
};

const els = {
  sensorStrip: document.getElementById("sensor-strip"),
  actuatorGrid: document.getElementById("actuator-grid"),
  chartGrid: document.getElementById("chart-grid"),
  decisionTimeline: document.getElementById("decision-timeline"),
  overrideTimeline: document.getElementById("override-timeline"),
  configDiff: document.getElementById("config-diff"),
  emergencyBanner: document.getElementById("emergency-banner"),
  toastStack: document.getElementById("toast-stack"),
  climateForm: document.getElementById("climate-form"),
  lightForm: document.getElementById("light-form"),
  wateringForm: document.getElementById("watering-form"),
  emergencyForm: document.getElementById("emergency-form"),
};

const FIELD_LABELS = {
  climate: "Climate",
  light: "Lighting",
  watering: "Watering",
  emergency: "Emergency",
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function loadGardenState() {
  const payload = await fetchJson("/api/garden/state");
  state.garden = payload;
  render();
}

function render() {
  if (!state.garden) {
    return;
  }
  renderEmergencyBanner();
  renderSensors();
  renderActuators();
  renderCharts();
  renderTimelines();
  renderConfigDiff();
  renderConfigForms();
}

function renderEmergencyBanner() {
  const emergency = state.garden.emergency;
  if (emergency.active) {
    els.emergencyBanner.hidden = false;
    els.emergencyBanner.textContent = emergency.message || "Emergency override active";
  } else {
    els.emergencyBanner.hidden = true;
  }
}

function renderSensors() {
  const tiles = [];
  for (const [sensorId, sensor] of Object.entries(state.garden.sensors)) {
    for (const metric of Object.values(sensor.metrics)) {
      tiles.push(`
        <article class="sensor-tile">
          <div class="sensor-tile__label">${sensor.label}</div>
          <div class="sensor-tile__value">${formatValue(metric.value)}</div>
          <div class="sensor-tile__unit">${metric.label}${metric.unit ? ` • ${metric.unit}` : ""}</div>
        </article>
      `);
    }
  }
  els.sensorStrip.innerHTML = tiles.join("");
}

function renderActuators() {
  const cards = Object.entries(state.garden.actuators).map(([actuatorId, actuator]) => {
    const pumpControls = actuatorId === "water_pump"
      ? `
        <button class="control-button is-primary" data-action="pulse" data-actuator="${actuatorId}" data-seconds="5">Pulse 5s</button>
        <button class="control-button" data-action="pulse" data-actuator="${actuatorId}" data-seconds="30">Pulse 30s</button>
      `
      : "";
    return `
      <article class="device-card">
        <div class="device-card__header">
          <div>
            <h3>${actuator.label}</h3>
            <p class="device-subtle">${actuator.driver}</p>
          </div>
          <span class="state-badge" data-state="${actuator.badge}">${actuator.badge}</span>
        </div>
        <p class="device-value">${actuator.power === true ? "ON" : actuator.power === false ? "OFF" : "UNKNOWN"}</p>
        <p class="device-subtle">${actuator.last_reason || "No recent decision reason"}</p>
        <div class="device-actions">
          <button class="control-button is-primary" data-action="on" data-actuator="${actuatorId}">On</button>
          <button class="control-button" data-action="off" data-actuator="${actuatorId}">Off</button>
          <button class="control-button" data-action="auto" data-actuator="${actuatorId}">Auto</button>
          ${pumpControls}
        </div>
        <div class="device-card__footer">
          <span class="device-subtle">${overrideText(actuator.override)}</span>
          <span class="device-subtle">${actuator.last_command_at ? new Date(actuator.last_command_at).toLocaleTimeString() : ""}</span>
        </div>
      </article>
    `;
  });
  els.actuatorGrid.innerHTML = cards.join("");
}

function renderCharts() {
  const cards = [];
  const chartDefs = [];
  for (const sensor of Object.values(state.garden.sensors)) {
    for (const [metricId, metric] of Object.entries(sensor.metrics)) {
      const canvasId = `${sensor.label}-${metricId}`.replaceAll(" ", "-");
      cards.push(`
        <article class="chart-card">
          <p class="panel-meta">${sensor.label}</p>
          <h3>${metric.label}</h3>
          <canvas id="${canvasId}" width="340" height="180"></canvas>
        </article>
      `);
      chartDefs.push({
        canvasId,
        points: sensor.history[metricId],
      });
    }
  }
  els.chartGrid.innerHTML = cards.join("");
  chartDefs.forEach(({ canvasId, points }) => {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
      drawLineChart(canvas, points);
    }
  });
}

function renderTimelines() {
  els.decisionTimeline.innerHTML = renderTimelineItems(
    state.garden.history.decision_history.map((item) => ({
      title: item.reason || item.decision,
      subtitle: `${item.decision || "control"} • ${formatTime(item.ts_utc)}`,
      detail: describeDecision(item),
    })),
  );

  els.overrideTimeline.innerHTML = renderTimelineItems(
    state.garden.history.manual_overrides.map((item) => ({
      title: `${item.actuator_id} • ${item.mode}`,
      subtitle: `${item.status} • ${formatTime(item.created_at_utc)}`,
      detail: item.reason || (item.pulse_seconds ? `Pulse ${item.pulse_seconds}s` : "Manual override"),
    })),
  );
}

function renderTimelineItems(items) {
  if (!items.length) {
    return '<p class="timeline-empty">No history yet.</p>';
  }
  return items.map((item) => `
    <article class="history-item">
      <strong>${item.title}</strong>
      <div class="history-item__meta">
        <span>${item.subtitle}</span>
      </div>
      <p class="device-subtle">${item.detail}</p>
    </article>
  `).join("");
}

function renderConfigDiff() {
  els.configDiff.textContent = JSON.stringify(state.garden.config.diff, null, 2);
}

function renderConfigForms() {
  renderClimateForm();
  renderLightForm();
  renderWateringForm();
  renderEmergencyForm();
}

function renderClimateForm() {
  const climate = state.garden.config.effective.climate;
  const simple = {
    temperature_on_above: climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.on_above ?? "",
    temperature_off_below: climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.off_below ?? "",
    humidity_on_above: climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.on_above ?? "",
    humidity_off_below: climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.off_below ?? "",
    heat_on_below: climate.heat?.bands?.[0]?.on_below ?? "",
    heat_off_above: climate.heat?.bands?.[0]?.off_above ?? "",
  };
  renderForm({
    form: els.climateForm,
    modeKey: "climate-config",
    simpleFields: [
      field("temperature_on_above", "Fan on above (C)", simple.temperature_on_above, "number"),
      field("temperature_off_below", "Fan off below (C)", simple.temperature_off_below, "number"),
      field("humidity_on_above", "Fan on above humidity (%)", simple.humidity_on_above, "number"),
      field("humidity_off_below", "Fan off below humidity (%)", simple.humidity_off_below, "number"),
      field("heat_on_below", "Pads on below (C)", simple.heat_on_below, "number"),
      field("heat_off_above", "Pads off above (C)", simple.heat_off_above, "number"),
    ],
    advancedValue: climate,
    submitLabel: "Save Climate",
    endpoint: "/api/config/garden/climate",
  });
}

function renderLightForm() {
  const light = state.garden.config.effective.light;
  renderForm({
    form: els.lightForm,
    modeKey: "light-config",
    simpleFields: [
      field("start", "Start", light.schedule.start, "time"),
      field("end", "End", light.schedule.end, "time"),
    ],
    advancedValue: light,
    submitLabel: "Save Lighting",
    endpoint: "/api/config/garden/lighting",
  });
}

function renderWateringForm() {
  const watering = state.garden.config.effective.watering;
  const fields = [
    selectField("watering_mode", "Mode", watering.mode, [
      ["schedule", "Timed schedule"],
      ["sensor", "Sensor driven"],
    ]),
    field("interval_minutes", "Interval minutes", watering.schedule?.interval_minutes ?? "", "number"),
    field("run_seconds", "Run seconds", watering.schedule?.run_seconds ?? "", "number"),
    field("anchor", "Anchor", watering.schedule?.anchor ?? "06:00", "time"),
    field("start_below", "Start below (%)", watering.sensor?.start_below ?? "", "number"),
    field("stop_above", "Stop above (%)", watering.sensor?.stop_above ?? "", "number"),
    field("max_run_seconds", "Max run seconds", watering.sensor?.max_run_seconds ?? "", "number"),
  ];
  renderForm({
    form: els.wateringForm,
    modeKey: "watering-config",
    simpleFields: fields,
    advancedValue: watering,
    submitLabel: "Save Watering",
    endpoint: "/api/config/garden/watering",
  });
}

function renderEmergencyForm() {
  const emergency = state.garden.config.effective.emergency;
  const actionsOff = emergency.actions.off.reduce((acc, action) => {
    acc[action.actuator] = action.command.power === false;
    return acc;
  }, {});
  renderForm({
    form: els.emergencyForm,
    modeKey: "emergency-config",
    simpleFields: [
      field("high_temp", "High temp emergency (C)", emergency.when.any?.find((item) => item.metric === "temperature_c")?.value ?? "", "number"),
      field("high_humidity", "High humidity emergency (%)", emergency.when.any?.find((item) => item.metric === "humidity_pct")?.value ?? "", "number"),
      checkboxField("fan_on", "Force fan on", true),
      checkboxField("lamps_off", "Force lamps off", actionsOff.lamps !== false),
      checkboxField("pads_off", "Force pads off", actionsOff.warm_pads !== false),
      checkboxField("pump_off", "Disable watering during emergency", actionsOff.water_pump === true),
    ],
    advancedValue: emergency,
    submitLabel: "Save Emergency",
    endpoint: "/api/config/garden/emergency",
  });
}

function renderForm({ form, modeKey, simpleFields, advancedValue, submitLabel, endpoint }) {
  const mode = state.configModes[modeKey];
  const body = mode === "advanced"
    ? `
      <label>
        Advanced JSON
        <textarea name="advanced">${JSON.stringify(advancedValue, null, 2)}</textarea>
      </label>
      <p class="config-help">Directly edit the validated controller block for ${FIELD_LABELS[modeKey.split("-")[0]] || "this module"}.</p>
    `
    : simpleFields.join("");
  form.innerHTML = `
    ${body}
    <div class="form-actions">
      <button class="utility-button" type="submit">${submitLabel}</button>
    </div>
  `;
  form.dataset.endpoint = endpoint;
  form.dataset.modeKey = modeKey;
}

function field(name, label, value, type = "text") {
  return `
    <label>
      ${label}
      <input name="${name}" type="${type}" value="${value ?? ""}">
    </label>
  `;
}

function checkboxField(name, label, checked) {
  return `
    <label>
      ${label}
      <select name="${name}">
        <option value="true" ${checked ? "selected" : ""}>Enabled</option>
        <option value="false" ${!checked ? "selected" : ""}>Disabled</option>
      </select>
    </label>
  `;
}

function selectField(name, label, value, options) {
  return `
    <label>
      ${label}
      <select name="${name}">
        ${options.map(([itemValue, itemLabel]) => `
          <option value="${itemValue}" ${itemValue === value ? "selected" : ""}>${itemLabel}</option>
        `).join("")}
      </select>
    </label>
  `;
}

function overrideText(override) {
  if (!override) {
    return "Auto mode";
  }
  const expires = override.expires_at_utc ? new Date(override.expires_at_utc).toLocaleTimeString() : "soon";
  if (override.mode === "pulse") {
    return `Pulse active until ${expires}`;
  }
  return `Manual ${override.mode.toUpperCase()} until ${expires}`;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "No data";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toString() : value.toFixed(1);
  }
  return String(value);
}

function formatTime(value) {
  if (!value) {
    return "";
  }
  return new Date(value).toLocaleString();
}

function describeDecision(item) {
  const results = item.payload?.action_results || [];
  if (!results.length) {
    return "No actuator change this cycle.";
  }
  return results.map((result) => `${result.actuator_id}: ${result.reason || result.command?.power}`).join(" • ");
}

function drawLineChart(canvas, points) {
  const context = canvas.getContext("2d");
  const values = points
    .map((point) => Number(point.value))
    .filter((value) => !Number.isNaN(value));
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.strokeStyle = "#3ad588";
  context.lineWidth = 2;
  context.fillStyle = "rgba(58, 213, 136, 0.12)";

  if (values.length < 2) {
    context.fillStyle = "#8fb39b";
    context.fillText("Not enough data", 12, 30);
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = 16;
  context.beginPath();
  values.forEach((value, index) => {
    const x = padding + (index / (values.length - 1)) * (canvas.width - padding * 2);
    const y = canvas.height - padding - ((value - min) / range) * (canvas.height - padding * 2);
    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  });
  context.stroke();
}

async function handleActuatorAction(event) {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }
  const actuatorId = button.dataset.actuator;
  const action = button.dataset.action;
  try {
    if (action === "auto") {
      await fetchJson(`/api/overrides/actuators/${actuatorId}`, { method: "DELETE" });
    } else {
      const payload = { mode: action, reason: "dashboard_control" };
      if (action === "pulse") {
        payload.pulse_seconds = Number(button.dataset.seconds || "5");
      }
      await fetchJson(`/api/overrides/actuators/${actuatorId}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    showToast(`Updated ${actuatorId}`);
    await runAutomationCycle();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function handleConfigSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const mode = state.configModes[form.dataset.modeKey];
  const endpoint = form.dataset.endpoint;
  const formData = new FormData(form);
  let payload = { mode };
  if (mode === "advanced") {
    payload.advanced = JSON.parse(formData.get("advanced"));
  } else {
    payload = {
      ...payload,
      ...Object.fromEntries(formData.entries()),
    };
    for (const [key, value] of Object.entries(payload)) {
      if (value === "true") payload[key] = true;
      else if (value === "false") payload[key] = false;
      else if (value !== "" && !Number.isNaN(Number(value)) && !String(value).includes(":")) payload[key] = Number(value);
    }
  }

  try {
    await fetchJson(endpoint, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    showToast("Config updated");
    await loadGardenState();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function runAutomationCycle() {
  try {
    await fetchJson("/api/automations/run", { method: "POST" });
  } catch (error) {
    showToast(error.message, true);
  }
  await loadGardenState();
}

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isError) {
    toast.style.borderColor = "rgba(255, 122, 122, 0.35)";
  }
  toast.textContent = message;
  els.toastStack.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function bindEvents() {
  els.actuatorGrid.addEventListener("click", handleActuatorAction);
  [els.climateForm, els.lightForm, els.wateringForm, els.emergencyForm].forEach((form) => {
    form.addEventListener("submit", handleConfigSubmit);
  });
  document.querySelectorAll(".mode-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.target;
      state.configModes[target] = state.configModes[target] === "simple" ? "advanced" : "simple";
      button.textContent = state.configModes[target] === "simple" ? "Advanced" : "Simple";
      renderConfigForms();
    });
  });
  document.getElementById("refresh-button").addEventListener("click", loadGardenState);
  document.getElementById("return-auto-button").addEventListener("click", async () => {
    await fetchJson("/api/garden/return-to-auto", { method: "POST" });
    showToast("All overrides cleared");
    await runAutomationCycle();
  });
  document.getElementById("safe-shutdown-button").addEventListener("click", async () => {
    await fetchJson("/api/garden/safe-shutdown", { method: "POST" });
    showToast("Safe shutdown requested");
    await runAutomationCycle();
  });
}

bindEvents();
loadGardenState().catch((error) => showToast(error.message, true));
setInterval(() => {
  loadGardenState().catch(() => {});
}, 15000);
