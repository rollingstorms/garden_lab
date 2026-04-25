const state = {
  garden: null,
  hoverRatio: null,
  configModes: {
    "climate-config": "simple",
    "light-config": "simple",
    "watering-config": "simple",
    "emergency-config": "simple",
  },
};

const chartStore = {};

const els = {
  emergencyBanner: document.getElementById("emergency-banner"),
  overviewDeck: document.getElementById("overview-deck"),
  sensorStrip: document.getElementById("sensor-strip"),
  actuatorGrid: document.getElementById("actuator-grid"),
  chartGrid: document.getElementById("chart-grid"),
  hoverReadout: document.getElementById("hover-readout"),
  decisionTimeline: document.getElementById("decision-timeline"),
  overrideTimeline: document.getElementById("override-timeline"),
  configDiff: document.getElementById("config-diff"),
  climateForm: document.getElementById("climate-form"),
  lightForm: document.getElementById("light-form"),
  wateringForm: document.getElementById("watering-form"),
  emergencyForm: document.getElementById("emergency-form"),
  climateSummary: document.getElementById("climate-summary"),
  lightSummary: document.getElementById("light-summary"),
  wateringSummary: document.getElementById("watering-summary"),
  emergencySummary: document.getElementById("emergency-summary"),
  toastStack: document.getElementById("toast-stack"),
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
  state.garden = await fetchJson("/api/garden/state");
  render();
}

function render() {
  if (!state.garden) return;
  renderEmergencyBanner();
  renderOverview();
  renderSensors();
  renderActuators();
  renderCharts();
  renderTimelines();
  renderConfigDiff();
  renderConfigSummaries();
  renderConfigForms();
}

function renderEmergencyBanner() {
  const emergency = state.garden.emergency;
  if (!emergency.active) {
    els.emergencyBanner.hidden = true;
    return;
  }
  els.emergencyBanner.hidden = false;
  els.emergencyBanner.innerHTML = `<strong>Emergency active.</strong> ${emergency.message || "Safety layer is holding the lab in a protected state."}`;
}

function renderOverview() {
  const activeOverrides = Object.values(state.garden.actuators).filter((item) => item.override).length;
  const decision = state.garden.decision || {};
  const cards = [
    overviewCard("Garden Mode", decision.reason === "garden_emergency" ? "Emergency" : "Balancing", decision.reason || "No cycle yet"),
    overviewCard("Manual Overrides", String(activeOverrides), activeOverrides ? "Temporary manual control active" : "All actuators in auto"),
    overviewCard("Last Decision", decision.decision || "Idle", decision.ts_utc ? formatTime(decision.ts_utc) : "No decision recorded"),
    overviewCard("Config Diff", String(Object.keys(state.garden.config.diff || {}).length), "Modules diverging from base config"),
  ];
  els.overviewDeck.innerHTML = cards.join("");
}

function overviewCard(label, value, sub) {
  return `
    <article class="overview-card">
      <div class="overview-card__label">${label}</div>
      <div class="overview-card__value">${value}</div>
      <div class="overview-card__sub">${sub}</div>
    </article>
  `;
}

function renderSensors() {
  const tiles = [];
  for (const sensor of Object.values(state.garden.sensors)) {
    for (const [metricId, metric] of Object.entries(sensor.metrics)) {
      const points = sensor.history[metricId] || [];
      const latestValue = metric.value;
      const previousValue = points.length > 1 ? points[points.length - 2].value : null;
      const delta = computeDelta(latestValue, previousValue);
      tiles.push(`
        <article class="sensor-tile">
          <div class="sensor-tile__label">${sensor.label}</div>
          <div class="sensor-tile__value">${formatValue(latestValue)}</div>
          <div class="sensor-tile__unit">${metric.label}${metric.unit ? ` • ${metric.unit}` : ""}</div>
          <div class="sensor-tile__trend">${delta}</div>
        </article>
      `);
    }
  }
  els.sensorStrip.innerHTML = tiles.join("");
}

function renderActuators() {
  els.actuatorGrid.innerHTML = Object.entries(state.garden.actuators)
    .map(([actuatorId, actuator]) => actuatorCard(actuatorId, actuator))
    .join("");
}

function actuatorCard(actuatorId, actuator) {
  const powerText = actuator.power === true ? "ON" : actuator.power === false ? "OFF" : "UNKNOWN";
  const pumpCluster = actuatorId === "water_pump"
    ? `
      <div class="control-cluster">
        <div class="cluster-label">Pulse</div>
        <div class="segmented-controls segmented-controls--pump">
          <button class="segmented-action is-primary" data-action="pulse" data-actuator="${actuatorId}" data-seconds="5">5s</button>
          <button class="segmented-action" data-action="pulse" data-actuator="${actuatorId}" data-seconds="30">30s</button>
          <button class="segmented-action" data-action="off" data-actuator="${actuatorId}">Off</button>
          <button class="segmented-action" data-action="auto" data-actuator="${actuatorId}">Auto</button>
          <button class="segmented-action" data-action="on" data-actuator="${actuatorId}">On</button>
        </div>
      </div>
    `
    : `
      <div class="control-cluster">
        <div class="cluster-label">Control</div>
        <div class="segmented-controls">
          <button class="segmented-action is-primary" data-action="on" data-actuator="${actuatorId}">On</button>
          <button class="segmented-action" data-action="off" data-actuator="${actuatorId}">Off</button>
          <button class="segmented-action" data-action="auto" data-actuator="${actuatorId}">Auto</button>
        </div>
      </div>
    `;
  return `
    <article class="device-card">
      <div class="device-card__header">
        <div>
          <h3>${actuator.label}</h3>
          <p class="device-card__driver">${actuator.driver}</p>
        </div>
        <span class="state-badge" data-state="${actuator.badge}">${actuator.badge}</span>
      </div>
      <div class="device-status">
        <div class="device-value-tile">
          <div class="device-value-label">Current State</div>
          <div class="device-value">${powerText}</div>
        </div>
        <div class="device-reason-tile">
          <div class="device-reason-label">Latest Reason</div>
          <div class="device-reason">${humanizeReason(actuator.last_reason || "No recent decision reason")}</div>
        </div>
      </div>
      ${pumpCluster}
      <div class="device-card__footer">
        <span>${overrideText(actuator.override)}</span>
        <span>${actuator.last_command_at ? formatShortTime(actuator.last_command_at) : "No command yet"}</span>
      </div>
    </article>
  `;
}

function renderCharts() {
  const defs = [];
  const cards = [];
  for (const [sensorId, sensor] of Object.entries(state.garden.sensors)) {
    for (const [metricId, metric] of Object.entries(sensor.metrics)) {
      const points = sensor.history[metricId] || [];
      const canvasId = `chart-${sensorId}-${metricId}`;
      defs.push({ canvasId, sensorLabel: sensor.label, metricLabel: metric.label, unit: metric.unit, points });
      cards.push(`
        <article class="chart-card">
          <div class="chart-card__heading">
            <div>
              <p class="panel-meta">${sensor.label}</p>
              <h3>${metric.label}</h3>
            </div>
            <div class="chart-card__stats">
              <strong>${formatValue(metric.value)}${metric.unit ? ` ${metric.unit}` : ""}</strong>
              ${points.length ? `${points.length} pts` : "No points"}
            </div>
          </div>
          <canvas id="${canvasId}" width="420" height="180"></canvas>
        </article>
      `);
    }
  }
  els.chartGrid.innerHTML = cards.join("");
  defs.forEach((def) => {
    const canvas = document.getElementById(def.canvasId);
    chartStore[def.canvasId] = def;
    attachHoverListeners(canvas, def);
    drawSeries(canvas, def);
  });
  updateHoverReadout();
}

function attachHoverListeners(canvas, def) {
  if (!canvas || canvas.dataset.bound === "true") return;
  const updateHover = (clientX) => {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(rect.width, 1)));
    state.hoverRatio = ratio;
    updateHoverReadout(def);
    redrawAllCharts();
  };
  canvas.addEventListener("mousemove", (event) => updateHover(event.clientX));
  canvas.addEventListener("mouseleave", () => {
    state.hoverRatio = null;
    updateHoverReadout();
    redrawAllCharts();
  });
  canvas.addEventListener("touchstart", (event) => {
    const touch = event.touches?.[0];
    if (touch) updateHover(touch.clientX);
  }, { passive: true });
  canvas.addEventListener("touchmove", (event) => {
    const touch = event.touches?.[0];
    if (touch) updateHover(touch.clientX);
  }, { passive: true });
  canvas.addEventListener("touchend", () => {
    state.hoverRatio = null;
    updateHoverReadout();
    redrawAllCharts();
  });
  canvas.dataset.bound = "true";
}

function redrawAllCharts() {
  Object.values(chartStore).forEach((def) => {
    const canvas = document.getElementById(def.canvasId);
    if (canvas) drawSeries(canvas, def);
  });
}

function drawSeries(canvas, def) {
  const context = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 420;
  const height = 180;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.scale(dpr, dpr);
  context.clearRect(0, 0, width, height);

  const points = def.points.filter((item) => item && item.value !== null && item.value !== undefined && !Number.isNaN(Number(item.value)));
  context.fillStyle = "rgba(255,255,255,0.02)";
  context.fillRect(0, 0, width, height);
  if (points.length === 0) {
    context.fillStyle = "#87ab97";
    context.font = "12px sans-serif";
    context.fillText("No chart data", 14, 26);
    return;
  }

  const values = points.map((item) => Number(item.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = { left: 42, right: 12, top: 12, bottom: 22 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const color = colorForMetric(def.metricLabel);

  for (let index = 0; index <= 3; index += 1) {
    const y = padding.top + (chartHeight * index) / 3;
    context.strokeStyle = "rgba(170, 232, 197, 0.12)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(padding.left, y);
    context.lineTo(width - padding.right, y);
    context.stroke();
  }

  const gradient = context.createLinearGradient(0, padding.top, 0, padding.top + chartHeight);
  gradient.addColorStop(0, hexToRgba(color, 0.34));
  gradient.addColorStop(1, hexToRgba(color, 0.02));

  context.beginPath();
  points.forEach((item, index) => {
    const x = pointX(index, points.length, padding.left, chartWidth);
    const y = pointY(Number(item.value), min, range, padding.top, chartHeight);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.lineTo(padding.left + chartWidth, padding.top + chartHeight);
  context.lineTo(padding.left, padding.top + chartHeight);
  context.closePath();
  context.fillStyle = gradient;
  context.fill();

  context.beginPath();
  points.forEach((item, index) => {
    const x = pointX(index, points.length, padding.left, chartWidth);
    const y = pointY(Number(item.value), min, range, padding.top, chartHeight);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.stroke();

  context.fillStyle = "#87ab97";
  context.font = "10px sans-serif";
  context.fillText(formatCompact(max), 6, padding.top + 8);
  context.fillText(formatCompact(min), 6, padding.top + chartHeight);
  const startLabel = formatShortTime(points[0].ts_utc);
  const endLabel = formatShortTime(points[points.length - 1].ts_utc);
  context.fillText(startLabel, padding.left, height - 5);
  const endWidth = context.measureText(endLabel).width;
  context.fillText(endLabel, width - padding.right - endWidth, height - 5);

  if (state.hoverRatio === null) return;
  const hoverIndex = Math.max(0, Math.min(points.length - 1, Math.round(state.hoverRatio * Math.max(points.length - 1, 1))));
  const hoverPoint = points[hoverIndex];
  const hoverX = pointX(hoverIndex, points.length, padding.left, chartWidth);
  const hoverY = pointY(Number(hoverPoint.value), min, range, padding.top, chartHeight);

  context.setLineDash([4, 4]);
  context.strokeStyle = "rgba(237, 249, 240, 0.55)";
  context.beginPath();
  context.moveTo(hoverX, padding.top);
  context.lineTo(hoverX, padding.top + chartHeight);
  context.stroke();
  context.setLineDash([]);

  context.fillStyle = color;
  context.beginPath();
  context.arc(hoverX, hoverY, 4, 0, Math.PI * 2);
  context.fill();

  const valueText = `${def.metricLabel}: ${formatValue(hoverPoint.value)}${def.unit ? ` ${def.unit}` : ""}`;
  const timeText = formatTime(hoverPoint.ts_utc);
  const pad = 6;
  context.font = "10px sans-serif";
  const tooltipWidth = Math.max(context.measureText(valueText).width, context.measureText(timeText).width) + pad * 2;
  const tooltipHeight = 32;
  let tooltipX = hoverX + 10;
  if (tooltipX + tooltipWidth > width - padding.right) tooltipX = hoverX - tooltipWidth - 10;
  const tooltipY = padding.top + 4;
  context.fillStyle = "rgba(8, 19, 18, 0.94)";
  roundRect(context, tooltipX, tooltipY, tooltipWidth, tooltipHeight, 10);
  context.fill();
  context.strokeStyle = "rgba(170, 232, 197, 0.22)";
  roundRect(context, tooltipX, tooltipY, tooltipWidth, tooltipHeight, 10);
  context.stroke();
  context.fillStyle = "#edf9f0";
  context.fillText(valueText, tooltipX + pad, tooltipY + 12);
  context.fillStyle = "#87ab97";
  context.fillText(timeText, tooltipX + pad, tooltipY + 24);
}

function roundRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + width, y, x + width, y + height, radius);
  context.arcTo(x + width, y + height, x, y + height, radius);
  context.arcTo(x, y + height, x, y, radius);
  context.arcTo(x, y, x + width, y, radius);
  context.closePath();
}

function renderTimelines() {
  els.decisionTimeline.innerHTML = renderTimelineItems(
    state.garden.history.decision_history.map((item) => ({
      title: humanizeReason(item.reason || item.decision || "Decision"),
      subtitle: `${item.decision || "control"} • ${formatTime(item.ts_utc)}`,
      detail: describeDecision(item),
    })),
  );

  els.overrideTimeline.innerHTML = renderTimelineItems(
    state.garden.history.manual_overrides.map((item) => ({
      title: `${labelizeActuator(item.actuator_id)} • ${item.mode}`,
      subtitle: `${item.status} • ${formatTime(item.created_at_utc)}`,
      detail: item.reason || (item.pulse_seconds ? `Pulse ${item.pulse_seconds}s` : "Manual override"),
    })),
  );
}

function renderTimelineItems(items) {
  if (!items.length) {
    return `<p class="timeline-empty">No history yet.</p>`;
  }
  return items.map((item) => `
    <article class="history-item">
      <strong>${item.title}</strong>
      <div class="history-item__meta"><span>${item.subtitle}</span></div>
      <div class="device-subtle">${item.detail}</div>
    </article>
  `).join("");
}

function renderConfigDiff() {
  els.configDiff.textContent = JSON.stringify(state.garden.config.diff, null, 2);
}

function renderConfigSummaries() {
  const climate = state.garden.config.effective.climate;
  const light = state.garden.config.effective.light;
  const watering = state.garden.config.effective.watering;
  const emergency = state.garden.config.effective.emergency;

  els.climateSummary.innerHTML = [
    chip("Fan temp", `${climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.off_below ?? "-"} to ${climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.on_above ?? "-"}`),
    chip("Humidity", `${climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.off_below ?? "-"} to ${climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.on_above ?? "-"}`),
    chip("Heat", `${climate.heat?.bands?.[0]?.on_below ?? "-"} to ${climate.heat?.bands?.[0]?.off_above ?? "-"}`),
  ].join("");

  els.lightSummary.innerHTML = [
    chip("Window", `${light.schedule.start} to ${light.schedule.end}`),
    chip("Actuator", labelizeActuator(light.actuator)),
  ].join("");

  els.wateringSummary.innerHTML = watering.mode === "schedule"
    ? [
        chip("Mode", "Timed"),
        chip("Interval", `${watering.schedule.interval_minutes} min`),
        chip("Run", `${watering.schedule.run_seconds}s`),
      ].join("")
    : [
        chip("Mode", "Sensor"),
        chip("Start below", `${watering.sensor.start_below}%`),
        chip("Stop above", `${watering.sensor.stop_above}%`),
      ].join("");

  els.emergencySummary.innerHTML = [
    chip("High temp", `${emergency.when.any?.find((item) => item.metric === "temperature_c")?.value ?? "-"} C`),
    chip("High humidity", `${emergency.when.any?.find((item) => item.metric === "humidity_pct")?.value ?? "-"} %`),
    chip("Actions", `${emergency.actions.off.length + emergency.actions.on.length} enforced`),
  ].join("");
}

function chip(label, value) {
  return `<span class="config-chip"><strong>${label}</strong>${value}</span>`;
}

function renderConfigForms() {
  renderClimateForm();
  renderLightForm();
  renderWateringForm();
  renderEmergencyForm();
}

function renderClimateForm() {
  const climate = state.garden.config.effective.climate;
  renderForm({
    form: els.climateForm,
    modeKey: "climate-config",
    simpleFields: [
      field("temperature_on_above", "Fan on above (C)", climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.on_above ?? "", "number"),
      field("temperature_off_below", "Fan off below (C)", climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.off_below ?? "", "number"),
      field("humidity_on_above", "Fan on above humidity (%)", climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.on_above ?? "", "number"),
      field("humidity_off_below", "Fan off below humidity (%)", climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.off_below ?? "", "number"),
      field("heat_on_below", "Pads on below (C)", climate.heat?.bands?.[0]?.on_below ?? "", "number"),
      field("heat_off_above", "Pads off above (C)", climate.heat?.bands?.[0]?.off_above ?? "", "number"),
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
      field("start", "Lights on", light.schedule.start, "time"),
      field("end", "Lights off", light.schedule.end, "time"),
    ],
    advancedValue: light,
    submitLabel: "Save Lighting",
    endpoint: "/api/config/garden/lighting",
  });
}

function renderWateringForm() {
  const watering = state.garden.config.effective.watering;
  renderForm({
    form: els.wateringForm,
    modeKey: "watering-config",
    simpleFields: [
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
    ],
    advancedValue: watering,
    submitLabel: "Save Watering",
    endpoint: "/api/config/garden/watering",
  });
}

function renderEmergencyForm() {
  const emergency = state.garden.config.effective.emergency;
  const offMap = Object.fromEntries(emergency.actions.off.map((item) => [item.actuator, item.command.power === false]));
  renderForm({
    form: els.emergencyForm,
    modeKey: "emergency-config",
    simpleFields: [
      field("high_temp", "Emergency high temp (C)", emergency.when.any?.find((item) => item.metric === "temperature_c")?.value ?? "", "number"),
      field("high_humidity", "Emergency high humidity (%)", emergency.when.any?.find((item) => item.metric === "humidity_pct")?.value ?? "", "number"),
      checkboxField("fan_on", "Force fan on", true),
      checkboxField("lamps_off", "Force lamps off", offMap.lamps !== false),
      checkboxField("pads_off", "Force pads off", offMap.warm_pads !== false),
      checkboxField("pump_off", "Disable watering", offMap.water_pump === true),
    ],
    advancedValue: emergency,
    submitLabel: "Save Emergency",
    endpoint: "/api/config/garden/emergency",
  });
}

function renderForm({ form, modeKey, simpleFields, advancedValue, submitLabel, endpoint }) {
  const mode = state.configModes[modeKey];
  const inner = mode === "advanced"
    ? `
      <label>
        Advanced JSON
        <textarea name="advanced">${JSON.stringify(advancedValue, null, 2)}</textarea>
      </label>
      <p class="config-help">Directly edit the validated controller block.</p>
    `
    : simpleFields.join("");
  form.innerHTML = `
    ${inner}
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

function selectField(name, label, value, options) {
  return `
    <label>
      ${label}
      <select name="${name}">
        ${options.map(([optionValue, optionLabel]) => `
          <option value="${optionValue}" ${optionValue === value ? "selected" : ""}>${optionLabel}</option>
        `).join("")}
      </select>
    </label>
  `;
}

function checkboxField(name, label, checked) {
  return `
    <label>
      ${label}
      <select name="${name}">
        <option value="true" ${checked ? "selected" : ""}>Enabled</option>
        <option value="false" ${checked ? "" : "selected"}>Disabled</option>
      </select>
    </label>
  `;
}

function updateHoverReadout(def = null) {
  if (state.hoverRatio === null) {
    els.hoverReadout.textContent = "Hover a chart for exact values.";
    return;
  }
  const activeDef = def || Object.values(chartStore)[0];
  if (!activeDef) {
    els.hoverReadout.textContent = "Hover a chart for exact values.";
    return;
  }
  const points = activeDef.points.filter((item) => item && item.value !== null && item.value !== undefined && !Number.isNaN(Number(item.value)));
  if (!points.length) {
    els.hoverReadout.textContent = "No chart data.";
    return;
  }
  const hoverIndex = Math.max(0, Math.min(points.length - 1, Math.round(state.hoverRatio * Math.max(points.length - 1, 1))));
  const point = points[hoverIndex];
  els.hoverReadout.textContent = `${activeDef.sensorLabel} • ${activeDef.metricLabel}: ${formatValue(point.value)}${activeDef.unit ? ` ${activeDef.unit}` : ""} • ${formatTime(point.ts_utc)}`;
}

function overrideText(override) {
  if (!override) return "Auto mode";
  if (override.mode === "pulse") return `Pulse active until ${formatShortTime(override.expires_at_utc)}`;
  return `Manual ${override.mode.toUpperCase()} until ${formatShortTime(override.expires_at_utc)}`;
}

function describeDecision(item) {
  const actions = item.payload?.action_results || [];
  if (!actions.length) return "No actuator changes in this cycle.";
  return actions.map((action) => `${labelizeActuator(action.actuator_id)}: ${humanizeReason(action.reason || action.source || "updated")}`).join(" • ");
}

function humanizeReason(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function labelizeActuator(actuatorId) {
  return String(actuatorId).replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function computeDelta(current, previous) {
  if (current === null || current === undefined || previous === null || previous === undefined) {
    return "Latest reading";
  }
  const numCurrent = Number(current);
  const numPrevious = Number(previous);
  if (Number.isNaN(numCurrent) || Number.isNaN(numPrevious)) return "Latest reading";
  const delta = numCurrent - numPrevious;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)} from previous sample`;
}

function colorForMetric(metricLabel) {
  const label = metricLabel.toLowerCase();
  if (label.includes("temperature")) return "#ff956a";
  if (label.includes("humidity")) return "#76c7ff";
  if (label.includes("light")) return "#ffd26a";
  if (label.includes("moisture")) return "#88f0b4";
  return "#b198ff";
}

function pointX(index, length, start, width) {
  return start + (width * index) / Math.max(length - 1, 1);
}

function pointY(value, min, range, start, height) {
  return start + height - ((value - min) / range) * height;
}

function hexToRgba(hex, alpha) {
  const clean = hex.replace("#", "");
  const expanded = clean.length === 3 ? clean.split("").map((char) => char + char).join("") : clean;
  const int = Number.parseInt(expanded, 16);
  const red = (int >> 16) & 255;
  const green = (int >> 8) & 255;
  const blue = int & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "No data";
  if (typeof value === "number") return Number.isInteger(value) ? value.toString() : value.toFixed(1);
  if (!Number.isNaN(Number(value)) && value !== "") {
    const num = Number(value);
    return Number.isInteger(num) ? num.toString() : num.toFixed(1);
  }
  return String(value);
}

function formatCompact(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(1);
}

function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString();
}

function formatShortTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString();
}

async function runAutomationCycle() {
  await fetchJson("/api/automations/run", { method: "POST" });
  await loadGardenState();
}

async function handleActuatorAction(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const actuatorId = button.dataset.actuator;
  const action = button.dataset.action;
  try {
    if (action === "auto") {
      await fetchJson(`/api/overrides/actuators/${actuatorId}`, { method: "DELETE" });
    } else {
      const payload = { mode: action, reason: "dashboard_control" };
      if (action === "pulse") payload.pulse_seconds = Number(button.dataset.seconds || "5");
      await fetchJson(`/api/overrides/actuators/${actuatorId}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    showToast(`Updated ${labelizeActuator(actuatorId)}`);
    await runAutomationCycle();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function handleConfigSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const mode = state.configModes[form.dataset.modeKey];
  const formData = new FormData(form);
  let payload = { mode };
  if (mode === "advanced") {
    payload.advanced = JSON.parse(formData.get("advanced"));
  } else {
    payload = { ...payload, ...Object.fromEntries(formData.entries()) };
    for (const [key, value] of Object.entries(payload)) {
      if (value === "true") payload[key] = true;
      else if (value === "false") payload[key] = false;
      else if (value !== "" && !String(value).includes(":") && !Number.isNaN(Number(value))) payload[key] = Number(value);
    }
  }
  try {
    await fetchJson(form.dataset.endpoint, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    showToast("Config updated");
    await loadGardenState();
  } catch (error) {
    showToast(error.message, true);
  }
}

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isError) toast.style.borderColor = "rgba(255, 127, 127, 0.34)";
  toast.textContent = message;
  els.toastStack.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function bindModeToggles() {
  document.querySelectorAll(".mode-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.target;
      state.configModes[target] = state.configModes[target] === "simple" ? "advanced" : "simple";
      button.textContent = state.configModes[target] === "simple" ? "Advanced" : "Simple";
      renderConfigForms();
    });
  });
}

function bindEvents() {
  els.actuatorGrid.addEventListener("click", handleActuatorAction);
  [els.climateForm, els.lightForm, els.wateringForm, els.emergencyForm].forEach((form) => {
    form.addEventListener("submit", handleConfigSubmit);
  });
  document.getElementById("refresh-button").addEventListener("click", loadGardenState);
  document.getElementById("return-auto-button").addEventListener("click", async () => {
    try {
      await fetchJson("/api/garden/return-to-auto", { method: "POST" });
      showToast("Returned every actuator to auto");
      await runAutomationCycle();
    } catch (error) {
      showToast(error.message, true);
    }
  });
  document.getElementById("safe-shutdown-button").addEventListener("click", async () => {
    try {
      await fetchJson("/api/garden/safe-shutdown", { method: "POST" });
      showToast("Safe shutdown requested");
      await runAutomationCycle();
    } catch (error) {
      showToast(error.message, true);
    }
  });
  bindModeToggles();
}

bindEvents();
loadGardenState().catch((error) => showToast(error.message, true));
setInterval(() => {
  loadGardenState().catch(() => {});
}, 15000);
