const MOBILE_BREAKPOINT = 980;

const ACTUATOR_COLORS = {
  exhaust_fan: "#22c55e",
  lamps: "#eab308",
  warm_pads: "#ef4444",
  water_pump: "#3b82f6",
};

const CHART_RANGE_OPTIONS = [
  { label: "1h", hours: 1 },
  { label: "3h", hours: 3 },
  { label: "6h", hours: 6 },
  { label: "12h", hours: 12 },
  { label: "24h", hours: 24 },
  { label: "3d", hours: 72 },
  { label: "7d", hours: 168 },
];

const DRUM_ITEM_H = 44;

const state = {
  garden: null,
  chartsData: null,
  historyData: null,
  configData: null,
  activeSection: "control",
  openConfig: null,
  optimisticActuators: {},
  chartHours: Number(window.localStorage.getItem("gardenLab.chartHours")) || 6,
  temperatureUnit: window.localStorage.getItem("gardenLab.temperatureUnit") || "C",
  inspect: {
    chartId: null,
    index: null,
    locked: false,
  },
  configModes: {
    "climate-config": "simple",
    "light-config": "simple",
    "watering-config": "simple",
    "emergency-config": "simple",
  },
};

const charts = {};

const els = {
  emergencyBanner: document.getElementById("emergency-banner"),
  overviewDeck: document.getElementById("overview-deck"),
  sensorStrip: document.getElementById("sensor-strip"),
  actuatorGrid: document.getElementById("actuator-grid"),
  chartGrid: document.getElementById("chart-grid"),
  actuatorTimeline: document.getElementById("actuator-timeline"),
  chartReadout: document.getElementById("hover-readout"),
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
  timezoneDisplay: document.getElementById("timezone-display"),
  toastStack: document.getElementById("toast-stack"),
};

function isMobileLayout() {
  return window.innerWidth < MOBILE_BREAKPOINT;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(formatApiError(payload, response.status));
  }
  return response.json();
}

function formatApiError(payload, status) {
  const detail = payload?.detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const path = Array.isArray(item?.loc) ? item.loc.slice(1).join(" > ") : "field";
        const message = item?.msg || "Invalid value";
        return `${path}: ${message}`;
      })
      .join(" | ");
  }
  if (typeof detail === "string" && detail) return detail;
  return `Request failed: ${status}`;
}

async function loadGardenState() {
  state.garden = await fetchJson("/api/garden/state");
  reconcileOptimisticActuators();
  render();
}

async function loadGardenCharts() {
  state.chartsData = await fetchJson(`/api/garden/charts?hours=${state.chartHours}`);
  renderCharts();
  updateChartReadout();
}

async function loadGardenHistory() {
  state.historyData = await fetchJson(`/api/garden/history?hours=${state.chartHours}`);
  renderTimelines();
}

async function loadGardenConfig() {
  state.configData = await fetchJson("/api/garden/config");
  renderOverview();
  renderConfigDiff();
  renderConfigSummaries();
  renderConfigPowerStates();
  renderConfigForms();
}

async function loadHeavyState() {
  await Promise.allSettled([
    loadGardenCharts(),
    loadGardenHistory(),
    loadGardenConfig(),
  ]);
}

function render() {
  if (!state.garden) return;
  syncSectionVisibility();
  renderEmergencyBanner();
  renderOverview();
  renderSensors();
  renderActuators();
  renderCharts();
  renderTimelines();
  renderConfigDiff();
  renderConfigSummaries();
  renderConfigAccordions();
  renderConfigPowerStates();
  renderConfigForms();
  renderFooter();
  updateChartReadout();
}

function syncSectionVisibility() {
  document.querySelectorAll("[data-section]").forEach((section) => {
    const active = section.dataset.section === state.activeSection;
    section.classList.toggle("is-active", active);
  });
  document.querySelectorAll("[data-section-tab]").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.sectionTab === state.activeSection);
  });
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
  const diffCount = state.configData?.diff ? Object.keys(state.configData.diff).length : "…";
  els.overviewDeck.innerHTML = [
    overviewCard("Garden Mode", decision.reason === "garden_emergency" ? "Emergency" : "Balancing", humanizeReason(decision.reason || "No cycle yet")),
    overviewCard("Manual Overrides", String(activeOverrides), activeOverrides ? "Temporary manual control active" : "All systems in auto"),
    overviewCard("Last Decision", decision.decision || "Idle", decision.ts_utc ? formatTime(decision.ts_utc) : "No decision recorded"),
    overviewCard("Config Diff", String(diffCount), "Modules diverging from base config"),
  ].join("");
}

function renderFooter() {
  const timezone = state.garden?.timezone || "America/New_York";
  els.timezoneDisplay.textContent = `Timezone: ${timezone}`;
  document.querySelectorAll("[data-temp-unit]").forEach((button) => {
    const active = button.dataset.tempUnit === state.temperatureUnit;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
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
      const previous = metric.previous ?? null;
      tiles.push(`
        <article class="sensor-tile">
          <div class="sensor-tile__label">${sensor.label}</div>
          <div class="sensor-tile__value">${formatMetricValue(metricId, metric.value)}</div>
          <div class="sensor-tile__unit">${metric.label}${displayMetricUnit(metricId, metric.unit) ? ` • ${displayMetricUnit(metricId, metric.unit)}` : ""}</div>
          <div class="sensor-tile__trend">${describeDelta(metricId, metric.value, previous)}</div>
        </article>
      `);
    }
  }
  els.sensorStrip.innerHTML = tiles.join("");
}

function renderActuators() {
  els.actuatorGrid.innerHTML = Object.entries(state.garden.actuators)
    .map(([actuatorId, actuator]) => renderActuatorCard(actuatorId, mergeActuatorState(actuatorId, actuator)))
    .join("");
}

function renderActuatorCard(actuatorId, actuator) {
  const powerText = actuator.power === true ? "ON" : actuator.power === false ? "OFF" : "No Live State";
  const lastCommandText = actuator.last_command_power === true ? "ON" : actuator.last_command_power === false ? "OFF" : "No command yet";
  const syncText = actuator.pending
    ? "Updating..."
    : `${humanizeReason(actuator.state_status || "unknown")} • ${humanizeReason(actuator.state_source || "unknown")}`;
  const activeAction = currentActuatorAction(actuatorId, actuator);
  const controls = actuatorId === "water_pump"
    ? `
      <div class="control-cluster">
        <div class="cluster-label">Pump Actions</div>
        <div class="segmented-controls segmented-controls--pump">
          <button class="segmented-action ${activeAction === "pulse-5" ? "is-primary" : ""}" aria-pressed="${String(activeAction === "pulse-5")}" data-action="pulse" data-actuator="${actuatorId}" data-seconds="5">Pulse 5s</button>
          <button class="segmented-action ${activeAction === "pulse-30" ? "is-primary" : ""}" aria-pressed="${String(activeAction === "pulse-30")}" data-action="pulse" data-actuator="${actuatorId}" data-seconds="30">Pulse 30s</button>
          <button class="segmented-action ${activeAction === "off" ? "is-primary" : ""}" aria-pressed="${String(activeAction === "off")}" data-action="off" data-actuator="${actuatorId}">Off</button>
          <button class="segmented-action ${activeAction === "auto" ? "is-primary" : ""}" aria-pressed="${String(activeAction === "auto")}" data-action="auto" data-actuator="${actuatorId}">Auto</button>
        </div>
      </div>
    `
    : `
      <div class="control-cluster">
        <div class="cluster-label">Device Mode</div>
        <div class="segmented-controls">
          <button class="segmented-action ${activeAction === "on" ? "is-primary" : ""}" aria-pressed="${String(activeAction === "on")}" data-action="on" data-actuator="${actuatorId}">On</button>
          <button class="segmented-action ${activeAction === "off" ? "is-primary" : ""}" aria-pressed="${String(activeAction === "off")}" data-action="off" data-actuator="${actuatorId}">Off</button>
          <button class="segmented-action ${activeAction === "auto" ? "is-primary" : ""}" aria-pressed="${String(activeAction === "auto")}" data-action="auto" data-actuator="${actuatorId}">Auto</button>
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
          <div class="device-value-label">Actual State</div>
          <div class="device-value">${powerText}</div>
        </div>
        <div class="device-reason-tile">
          <div class="device-reason-label">Last Reason</div>
          <div class="device-reason">${humanizeReason(actuator.last_reason || "No recent decision reason")}</div>
        </div>
      </div>

      ${controls}

      <div class="device-card__footer">
        <span>${overrideText(actuator.override)}</span>
        <span>Last command: ${lastCommandText}${actuator.last_command_at ? ` • ${formatShortTime(actuator.last_command_at)}` : ""}</span>
      </div>
      <div class="device-card__footer">
        <span>${syncText}</span>
        <span>${actuator.last_seen_at ? `Seen ${formatShortTime(actuator.last_seen_at)}` : "Awaiting live state"}</span>
      </div>
    </article>
  `;
}

function currentActuatorAction(actuatorId, actuator) {
  if (!actuator.override) return "auto";
  if (actuator.override.mode === "pulse") {
    const seconds = Number(actuator.override.pulse_seconds || 0);
    if (seconds === 30) return "pulse-30";
    return "pulse-5";
  }
  if (actuator.override.mode === "on") return "on";
  if (actuator.override.mode === "off") return "off";
  return actuatorId === "water_pump" ? "auto" : "auto";
}

function mergeActuatorState(actuatorId, actuator) {
  return state.optimisticActuators[actuatorId]
    ? { ...actuator, ...state.optimisticActuators[actuatorId] }
    : actuator;
}

function reconcileOptimisticActuators() {
  if (!state.garden) return;
  Object.keys(state.optimisticActuators).forEach((actuatorId) => {
    const actual = state.garden.actuators[actuatorId];
    if (!actual) {
      delete state.optimisticActuators[actuatorId];
      return;
    }
    const pending = state.optimisticActuators[actuatorId];
    if (!pending) return;
    if (actual.override?.mode === pending.override?.mode || (!actual.override && !pending.override)) {
      delete state.optimisticActuators[actuatorId];
    }
  });
}

function currentEffectiveConfig() {
  return state.configData?.effective || state.garden?.config?.effective || null;
}

function optimisticActuatorState(actuatorId, actuator, button) {
  const action = button.dataset.action;
  if (action === "auto") {
    return {
      override: null,
      badge: "auto",
      pending: true,
    };
  }
  if (action === "pulse") {
    return {
      power: true,
      badge: "pulse",
      override: {
        mode: "pulse",
        pulse_seconds: Number(button.dataset.seconds || "5"),
      },
      pending: true,
      state_status: "pending",
      state_source: "live",
    };
  }
  return {
    power: action === "on",
    badge: "manual",
    override: {
      mode: action,
    },
    pending: true,
    state_status: "pending",
    state_source: "live",
    last_reason: "pending_update",
  };
}

function buildActuatorSpans(events, windowStart, windowEnd) {
  const byActuator = {};
  for (const event of events) {
    const power = event.payload?.command?.power ?? event.payload?.state?.power;
    if (typeof power !== "boolean") continue;
    if (!byActuator[event.actuator_id]) byActuator[event.actuator_id] = [];
    byActuator[event.actuator_id].push({ ts: new Date(event.ts_utc).getTime(), power });
  }
  const spans = {};
  for (const [actuatorId, evts] of Object.entries(byActuator)) {
    const sorted = [...evts].sort((a, b) => a.ts - b.ts);
    spans[actuatorId] = [];
    // If the oldest event in our window is "off", the device may have been on before the window.
    // Peek at the last event *before* windowStart to seed the initial state.
    const beforeWindow = sorted.filter((e) => e.ts < windowStart);
    const inWindow = sorted.filter((e) => e.ts >= windowStart);
    const seedPower = beforeWindow.length ? beforeWindow[beforeWindow.length - 1].power : null;
    let onStart = seedPower === true ? windowStart : null;
    for (const evt of inWindow) {
      if (evt.power && onStart === null) {
        onStart = evt.ts;
      } else if (!evt.power && onStart !== null) {
        spans[actuatorId].push({ start: onStart, end: evt.ts });
        onStart = null;
      }
    }
    if (onStart !== null) {
      spans[actuatorId].push({ start: onStart, end: windowEnd });
    }
  }
  return spans;
}

function drawActuatorTimeline() {
  const canvas = els.actuatorTimeline;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const actuatorOrder = state.garden ? Object.keys(state.garden.actuators) : Object.keys(ACTUATOR_COLORS);
  const labels = state.garden
    ? Object.fromEntries(Object.entries(state.garden.actuators).map(([id, a]) => [id, a.label]))
    : {};

  const events = state.historyData?.history?.actuator_events || [];
  const now = Date.now();
  const windowStart = now - state.chartHours * 60 * 60 * 1000;
  const windowEnd = now;
  const spans = buildActuatorSpans(events, windowStart, windowEnd);

  const ROW_H = 24;
  const ROW_GAP = 5;
  const LABEL_W = 90;
  const PAD_TOP = 10;
  const PAD_BOT = 20;
  const cssWidth = canvas.parentElement?.clientWidth || 420;
  const totalH = PAD_TOP + actuatorOrder.length * (ROW_H + ROW_GAP) - ROW_GAP + PAD_BOT;

  canvas.width = cssWidth;
  canvas.height = totalH;
  canvas.style.width = cssWidth + "px";
  canvas.style.height = totalH + "px";

  ctx.clearRect(0, 0, cssWidth, totalH);
  const barW = cssWidth - LABEL_W - 8;
  const timeRange = windowEnd - windowStart;

  for (let i = 0; i < actuatorOrder.length; i++) {
    const actuatorId = actuatorOrder[i];
    const y = PAD_TOP + i * (ROW_H + ROW_GAP);
    const color = ACTUATOR_COLORS[actuatorId] || "#666";

    ctx.fillStyle = "rgba(255,255,255,0.04)";
    roundRect(ctx, LABEL_W, y, barW, ROW_H, 4);
    ctx.fill();

    ctx.fillStyle = color;
    for (const span of (spans[actuatorId] || [])) {
      const cs = Math.max(span.start, windowStart);
      const ce = Math.min(span.end, windowEnd);
      if (ce <= cs) continue;
      const x = LABEL_W + ((cs - windowStart) / timeRange) * barW;
      const w = Math.max(2, ((ce - cs) / timeRange) * barW);
      roundRect(ctx, x, y, w, ROW_H, 4);
      ctx.fill();
    }

    ctx.fillStyle = "#92b09d";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    ctx.fillText(labels[actuatorId] || actuatorId, 0, y + ROW_H / 2);
  }

  const ticks = 4;
  for (let t = 0; t <= ticks; t++) {
    const ratio = t / ticks;
    const x = LABEL_W + ratio * barW;
    ctx.strokeStyle = "rgba(172, 229, 197, 0.1)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, PAD_TOP);
    ctx.lineTo(x, PAD_TOP + actuatorOrder.length * (ROW_H + ROW_GAP) - ROW_GAP);
    ctx.stroke();
    const d = new Date(windowStart + ratio * timeRange);
    const label = state.chartHours <= 24
      ? `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
      : `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}h`;
    ctx.fillStyle = "#555";
    ctx.font = "9px system-ui, sans-serif";
    ctx.textBaseline = "top";
    ctx.textAlign = "center";
    ctx.fillText(
      label,
      x,
      PAD_TOP + actuatorOrder.length * (ROW_H + ROW_GAP) - ROW_GAP + 4,
    );
  }
}

function renderCharts() {
  if (!state.chartsData?.sensors) {
    els.chartGrid.innerHTML = `<article class="chart-card"><div class="chart-card__heading"><div><p class="panel-meta">History</p><h3>Loading charts</h3></div></div></article>`;
    return;
  }
  const defs = [];
  const cards = [];
  for (const [sensorId, sensor] of Object.entries(state.chartsData.sensors)) {
    for (const [metricId, metric] of Object.entries(sensor.metrics)) {
      const points = (sensor.history[metricId] || []).filter((item) => item && item.value !== null && item.value !== undefined && !Number.isNaN(Number(item.value)));
      const chartId = `chart-${sensorId}-${metricId}`;
      const min = points.length ? Math.min(...points.map((item) => Number(item.value))) : null;
      const max = points.length ? Math.max(...points.map((item) => Number(item.value))) : null;
      defs.push({
        chartId,
        sensorLabel: sensor.label,
        metricId,
        metricLabel: metric.label,
        unit: metric.unit,
        points,
      });
      cards.push(`
        <article class="chart-card" data-chart-card="${chartId}">
          <div class="chart-card__heading">
            <div>
              <p class="panel-meta">${sensor.label}</p>
              <h3>${metric.label}</h3>
            </div>
            <div class="chart-card__stats">
              <strong>${formatMetricValue(metricId, metric.value)}${displayMetricUnit(metricId, metric.unit) ? ` ${displayMetricUnit(metricId, metric.unit)}` : ""}</strong>
              ${min !== null && max !== null ? `${formatMetricValue(metricId, min)} - ${formatMetricValue(metricId, max)}` : "No range"}
            </div>
          </div>
          <canvas id="${chartId}" width="420" height="180"></canvas>
        </article>
      `);
    }
  }

  els.chartGrid.innerHTML = cards.join("");
  Object.keys(charts).forEach((key) => delete charts[key]);
  defs.forEach((def) => {
    charts[def.chartId] = def;
    const canvas = document.getElementById(def.chartId);
    attachChartListeners(canvas, def);
    drawSeries(canvas, def);
  });
}

function attachChartListeners(canvas, def) {
  if (!canvas || canvas.dataset.bound === "true") return;

  const setFromClientX = (clientX, lock = false) => {
    if (!def.points.length) return;
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(rect.width, 1)));
    const index = Math.max(0, Math.min(def.points.length - 1, Math.round(ratio * Math.max(def.points.length - 1, 1))));
    state.inspect = {
      chartId: def.chartId,
      index,
      locked: lock,
    };
    redrawAllCharts();
    updateChartReadout();
  };

  canvas.addEventListener("mousemove", (event) => {
    if (isMobileLayout() || (state.inspect.locked && state.inspect.chartId === def.chartId)) return;
    setFromClientX(event.clientX, false);
  });

  canvas.addEventListener("mouseleave", () => {
    if (isMobileLayout() || state.inspect.locked) return;
    clearInspect();
  });

  canvas.addEventListener("click", (event) => {
    if (!def.points.length) return;
    if (state.inspect.locked && state.inspect.chartId === def.chartId) {
      clearInspect();
      return;
    }
    setFromClientX(event.clientX, true);
  });

  canvas.addEventListener(
    "touchstart",
    (event) => {
      const touch = event.touches?.[0];
      if (!touch) return;
      setFromClientX(touch.clientX, true);
    },
    { passive: true },
  );

  canvas.addEventListener(
    "touchmove",
    (event) => {
      if (!state.inspect.locked || state.inspect.chartId !== def.chartId) return;
      const touch = event.touches?.[0];
      if (!touch) return;
      setFromClientX(touch.clientX, true);
    },
    { passive: true },
  );

  canvas.dataset.bound = "true";
}

function redrawAllCharts() {
  Object.values(charts).forEach((def) => {
    const canvas = document.getElementById(def.chartId);
    if (canvas) drawSeries(canvas, def);
  });
  drawActuatorTimeline();
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

  const points = def.points;
  context.fillStyle = "rgba(255,255,255,0.02)";
  context.fillRect(0, 0, width, height);

  if (!points.length) {
    context.fillStyle = "#92b09d";
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
  const color = metricColor(def.metricLabel);

  for (let index = 0; index <= 3; index += 1) {
    const y = padding.top + (chartHeight * index) / 3;
    context.strokeStyle = "rgba(172, 229, 197, 0.12)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(padding.left, y);
    context.lineTo(width - padding.right, y);
    context.stroke();
  }

  const fill = context.createLinearGradient(0, padding.top, 0, padding.top + chartHeight);
  fill.addColorStop(0, hexToRgba(color, 0.34));
  fill.addColorStop(1, hexToRgba(color, 0.02));

  context.beginPath();
  points.forEach((point, index) => {
    const x = pointX(index, points.length, padding.left, chartWidth);
    const y = pointY(Number(point.value), min, range, padding.top, chartHeight);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.lineTo(padding.left + chartWidth, padding.top + chartHeight);
  context.lineTo(padding.left, padding.top + chartHeight);
  context.closePath();
  context.fillStyle = fill;
  context.fill();

  context.beginPath();
  points.forEach((point, index) => {
    const x = pointX(index, points.length, padding.left, chartWidth);
    const y = pointY(Number(point.value), min, range, padding.top, chartHeight);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.stroke();

  context.fillStyle = "#92b09d";
  context.font = "10px sans-serif";
  context.fillText(formatMetricCompact(def.metricId, max), 6, padding.top + 8);
  context.fillText(formatMetricCompact(def.metricId, min), 6, padding.top + chartHeight);
  const start = formatShortTime(points[0].ts_utc);
  const end = formatShortTime(points[points.length - 1].ts_utc);
  context.fillText(start, padding.left, height - 5);
  context.fillText(end, width - padding.right - context.measureText(end).width, height - 5);

  if (state.inspect.chartId !== def.chartId || state.inspect.index === null) return;
  const hoverPoint = points[Math.max(0, Math.min(points.length - 1, state.inspect.index))];
  const hoverX = pointX(state.inspect.index, points.length, padding.left, chartWidth);
  const hoverY = pointY(Number(hoverPoint.value), min, range, padding.top, chartHeight);

  context.setLineDash([4, 4]);
  context.strokeStyle = "rgba(238, 249, 241, 0.55)";
  context.beginPath();
  context.moveTo(hoverX, padding.top);
  context.lineTo(hoverX, padding.top + chartHeight);
  context.stroke();
  context.setLineDash([]);

  context.fillStyle = color;
  context.beginPath();
  context.arc(hoverX, hoverY, 4, 0, Math.PI * 2);
  context.fill();

  if (!isMobileLayout()) {
    drawTooltip(context, {
      x: hoverX,
      y: padding.top + 4,
      width,
      paddingRight: padding.right,
      valueText: `${def.metricLabel}: ${formatMetricValue(def.metricId, hoverPoint.value)}${displayMetricUnit(def.metricId, def.unit) ? ` ${displayMetricUnit(def.metricId, def.unit)}` : ""}`,
      timeText: formatTime(hoverPoint.ts_utc),
    });
  }
}

function drawTooltip(context, options) {
  const pad = 6;
  context.font = "10px sans-serif";
  const tooltipWidth = Math.max(
    context.measureText(options.valueText).width,
    context.measureText(options.timeText).width,
  ) + pad * 2;
  const tooltipHeight = 32;
  let tooltipX = options.x + 10;
  if (tooltipX + tooltipWidth > options.width - options.paddingRight) tooltipX = options.x - tooltipWidth - 10;
  const tooltipY = options.y;
  context.fillStyle = "rgba(8, 18, 17, 0.96)";
  roundRect(context, tooltipX, tooltipY, tooltipWidth, tooltipHeight, 10);
  context.fill();
  context.strokeStyle = "rgba(172, 229, 197, 0.2)";
  roundRect(context, tooltipX, tooltipY, tooltipWidth, tooltipHeight, 10);
  context.stroke();
  context.fillStyle = "#eef9f1";
  context.fillText(options.valueText, tooltipX + pad, tooltipY + 12);
  context.fillStyle = "#92b09d";
  context.fillText(options.timeText, tooltipX + pad, tooltipY + 24);
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

function updateChartReadout() {
  if (!state.inspect.chartId || state.inspect.index === null) {
    els.chartReadout.textContent = isMobileLayout()
      ? "Tap a chart to inspect exact values."
      : "Hover or tap a chart for exact values.";
    return;
  }
  const def = charts[state.inspect.chartId];
  if (!def || !def.points.length) {
    els.chartReadout.textContent = "No chart data.";
    return;
  }
  const point = def.points[Math.max(0, Math.min(def.points.length - 1, state.inspect.index))];
  els.chartReadout.textContent = `${def.sensorLabel} • ${def.metricLabel}: ${formatMetricValue(def.metricId, point.value)}${displayMetricUnit(def.metricId, def.unit) ? ` ${displayMetricUnit(def.metricId, def.unit)}` : ""} • ${formatTime(point.ts_utc)}`;
}

function clearInspect() {
  state.inspect = { chartId: null, index: null, locked: false };
  redrawAllCharts();
  updateChartReadout();
}

function renderTimelines() {
  if (!state.historyData?.history) {
    els.decisionTimeline.innerHTML = `<p class="timeline-empty">Loading history…</p>`;
    els.overrideTimeline.innerHTML = `<p class="timeline-empty">Loading history…</p>`;
    return;
  }
  els.decisionTimeline.innerHTML = renderTimelineItems(
    state.historyData.history.decision_history.map((item) => ({
      title: humanizeReason(item.reason || item.decision || "Decision"),
      subtitle: `${item.decision || "control"} • ${formatTime(item.ts_utc)}`,
      detail: describeDecision(item),
    })),
  );

  els.overrideTimeline.innerHTML = renderTimelineItems(
    state.historyData.history.manual_overrides.map((item) => ({
      title: `${labelizeActuator(item.actuator_id)} • ${item.mode}`,
      subtitle: `${item.status} • ${formatTime(item.created_at_utc)}`,
      detail: item.reason || (item.pulse_seconds ? `Pulse ${item.pulse_seconds}s` : "Manual override"),
    })),
  );
  drawActuatorTimeline();
}

function renderTimelineItems(items) {
  if (!items.length) return `<p class="timeline-empty">No history yet.</p>`;
  return items.map((item) => `
    <article class="history-item">
      <strong>${item.title}</strong>
      <div class="history-item__meta"><span>${item.subtitle}</span></div>
      <div class="device-subtle">${item.detail}</div>
    </article>
  `).join("");
}

function renderConfigDiff() {
  els.configDiff.textContent = state.configData
    ? JSON.stringify(state.configData.diff, null, 2)
    : "Loading config diff…";
}

function renderConfigSummaries() {
  const effectiveConfig = currentEffectiveConfig();
  if (!effectiveConfig) return;
  const climate = effectiveConfig.climate;
  const light = effectiveConfig.light;
  const watering = effectiveConfig.watering;
  const emergency = effectiveConfig.emergency;

  els.climateSummary.innerHTML = [
    chip("State", climate.enabled === false ? "Off" : "On"),
    chip("Fan temp", `${formatMetricValue("temperature_c", climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.off_below)} to ${formatMetricValue("temperature_c", climate.fan?.bands?.find((band) => band.metric === "temperature_c")?.on_above)}`),
    chip("Humidity", `${climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.off_below ?? "-"} to ${climate.fan?.bands?.find((band) => band.metric === "humidity_pct")?.on_above ?? "-"}`),
    chip("Heat", `${formatMetricValue("temperature_c", climate.heat?.bands?.[0]?.on_below)} to ${formatMetricValue("temperature_c", climate.heat?.bands?.[0]?.off_above)}`),
  ].join("");

  els.lightSummary.innerHTML = [
    chip("State", light.enabled === false ? "Off" : "On"),
    chip("Window", `${light.schedule.start} to ${light.schedule.end}`),
    chip("Actuator", labelizeActuator(light.actuator)),
  ].join("");

  els.wateringSummary.innerHTML = watering.mode === "schedule"
    ? [
        chip("State", watering.enabled === false ? "Off" : "On"),
        chip("Mode", "Timed"),
        chip("Interval", `${watering.schedule.interval_minutes} min`),
        chip("Run", `${watering.schedule.run_seconds}s`),
      ].join("")
    : [
        chip("State", watering.enabled === false ? "Off" : "On"),
        chip("Mode", "Sensor"),
        chip("Start below", `${watering.sensor.start_below}%`),
        chip("Stop above", `${watering.sensor.stop_above}%`),
      ].join("");

  els.emergencySummary.innerHTML = [
    chip("State", emergency.enabled === false ? "Off" : "On"),
    chip("High temp", `${formatMetricValue("temperature_c", emergency.when.any?.find((item) => item.metric === "temperature_c")?.value)} ${displayMetricUnit("temperature_c", "C")}`),
    chip("High humidity", `${emergency.when.any?.find((item) => item.metric === "humidity_pct")?.value ?? "-"} %`),
    chip("Actions", `${emergency.actions.on.length + emergency.actions.off.length} enforced`),
  ].join("");
}

function renderConfigAccordions() {
  const cards = document.querySelectorAll("[data-config-card]");
  cards.forEach((card) => {
    const name = card.dataset.configCard;
    const open = state.openConfig === name;
    card.classList.toggle("is-open", open);
    const editor = card.querySelector(".config-card__editor");
    if (editor) editor.hidden = !open;
    const label = card.querySelector(".config-card__toggle-label");
    if (label) label.textContent = open ? "Close" : "Open";
  });
}

function renderConfigPowerStates() {
  const modules = currentEffectiveConfig() || {};
  document.querySelectorAll("[data-config-power-group]").forEach((group) => {
    const module = group.dataset.configPowerGroup;
    const enabled = modules[module]?.enabled !== false;
    group.querySelectorAll("[data-config-power]").forEach((button) => {
      const active = String(enabled) === button.dataset.enabled;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const card = group.closest("[data-config-card]");
    if (card) card.classList.toggle("is-disabled", !enabled);
  });
}

function renderConfigForms() {
  renderClimateForm();
  renderLightForm();
  renderWateringForm();
  renderEmergencyForm();
}

function renderClimateForm() {
  const climate = currentEffectiveConfig().climate;
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
  const light = currentEffectiveConfig().light;
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
  const watering = currentEffectiveConfig().watering;
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
  const emergency = currentEffectiveConfig().emergency;
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
  const body = mode === "advanced"
    ? `
      <label>
        Advanced JSON
        <textarea name="advanced">${JSON.stringify(advancedValue, null, 2)}</textarea>
      </label>
      <p class="config-help">Directly edit the validated controller block.</p>
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

function chip(label, value) {
  return `<span class="config-chip"><strong>${label}</strong>${value}</span>`;
}

function metricColor(label) {
  const value = label.toLowerCase();
  if (value.includes("temperature")) return "#ff9a68";
  if (value.includes("humidity")) return "#78cfff";
  if (value.includes("light")) return "#ffd970";
  if (value.includes("moisture")) return "#6ef0a5";
  return "#8ec8ff";
}

function pointX(index, length, start, width) {
  return start + (width * index) / Math.max(length - 1, 1);
}

function pointY(value, min, range, start, height) {
  return start + height - ((value - min) / range) * height;
}

function hexToRgba(hex, alpha) {
  const normalized = hex.replace("#", "");
  const expanded = normalized.length === 3 ? normalized.split("").map((item) => item + item).join("") : normalized;
  const int = Number.parseInt(expanded, 16);
  const red = (int >> 16) & 255;
  const green = (int >> 8) & 255;
  const blue = int & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "No data";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(1);
  if (!Number.isNaN(Number(value)) && value !== "") {
    const num = Number(value);
    return Number.isInteger(num) ? String(num) : num.toFixed(1);
  }
  return String(value);
}

function formatCompact(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(1);
}

function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString([], {
    timeZone: state.garden?.timezone || "America/New_York",
  });
}

function formatShortTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], {
    timeZone: state.garden?.timezone || "America/New_York",
    hour: "numeric",
    minute: "2-digit",
  });
}

function describeDelta(metricId, current, previous) {
  if (current === null || current === undefined || previous === null || previous === undefined) return "Latest reading";
  const currentNum = Number(current);
  const previousNum = Number(previous);
  if (Number.isNaN(currentNum) || Number.isNaN(previousNum)) return "Latest reading";
  const delta = convertMetricValue(metricId, currentNum) - convertMetricValue(metricId, previousNum);
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)} from previous sample`;
}

function isTemperatureMetric(metricId, unit = "") {
  return String(metricId).toLowerCase().includes("temperature") || String(unit).toUpperCase() === "C";
}

function convertTemperature(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return value;
  if (state.temperatureUnit === "F") return (Number(value) * 9) / 5 + 32;
  return Number(value);
}

function convertMetricValue(metricId, value, unit = "") {
  if (isTemperatureMetric(metricId, unit)) return convertTemperature(value);
  return Number(value);
}

function formatMetricValue(metricId, value, unit = "") {
  if (value === null || value === undefined || value === "") return "No data";
  if (Number.isNaN(Number(value))) return String(value);
  const converted = convertMetricValue(metricId, value, unit);
  return Number.isInteger(converted) ? String(converted) : converted.toFixed(1);
}

function formatMetricCompact(metricId, value, unit = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return convertMetricValue(metricId, value, unit).toFixed(1);
}

function displayMetricUnit(metricId, unit = "") {
  if (isTemperatureMetric(metricId, unit)) return state.temperatureUnit;
  return unit || "";
}

function humanizeReason(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function labelizeActuator(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function overrideText(override) {
  if (!override) return "Auto mode";
  if (override.mode === "pulse") return `Pulse active until ${formatShortTime(override.expires_at_utc)}`;
  return `Manual ${override.mode.toUpperCase()} until ${formatShortTime(override.expires_at_utc)}`;
}

function describeDecision(item) {
  const actions = item.payload?.action_results || [];
  if (!actions.length) return "No actuator changes in this cycle.";
  return actions
    .map((action) => `${labelizeActuator(action.actuator_id)}: ${humanizeReason(action.reason || "updated")}`)
    .join(" • ");
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
  const current = state.garden?.actuators?.[actuatorId];
  if (!current) return;
  state.optimisticActuators[actuatorId] = optimisticActuatorState(actuatorId, current, button);
  renderActuators();

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
    loadGardenState().catch(() => {});
  } catch (error) {
    delete state.optimisticActuators[actuatorId];
    renderActuators();
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
    await fetchJson("/api/automations/run", { method: "POST" }).catch(() => {});
    await Promise.allSettled([loadGardenState(), loadGardenConfig(), loadGardenHistory()]);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function handleConfigPower(event) {
  const button = event.target.closest("[data-config-power]");
  if (!button) return;
  const module = button.dataset.configPower;
  const enabled = button.dataset.enabled === "true";
  if (button.classList.contains("is-active")) return;
  try {
    await fetchJson(`/api/config/garden/${module}/enabled`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    showToast(`${labelizeActuator(module)} ${enabled ? "enabled" : "disabled"}.`);
    await fetchJson("/api/automations/run", { method: "POST" }).catch(() => {});
    await Promise.allSettled([loadGardenState(), loadGardenConfig(), loadGardenHistory()]);
  } catch (error) {
    showToast(error.message, true);
  }
}

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isError) toast.style.borderColor = "rgba(255, 127, 141, 0.34)";
  toast.textContent = message;
  els.toastStack.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function bindSectionTabs() {
  document.querySelectorAll("[data-section-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeSection = button.dataset.sectionTab;
      syncSectionVisibility();
    });
  });
}

function bindConfigAccordions() {
  document.querySelectorAll("[data-config-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.configToggle;
      state.openConfig = state.openConfig === target ? null : target;
      if (isMobileLayout()) {
        document.querySelectorAll("[data-config-card]").forEach((card) => {
          if (card.dataset.configCard !== target) card.classList.remove("is-open");
        });
      }
      renderConfigAccordions();
    });
  });
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

function bindUtilityActions() {
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
  document.getElementById("reset-config-button").addEventListener("click", async () => {
    try {
      await fetchJson("/api/config/garden/reset", { method: "POST" });
      showToast("Garden config reset to defaults");
      await loadGardenState();
    } catch (error) {
      showToast(error.message, true);
    }
  });
  document.querySelectorAll("[data-temp-unit]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.tempUnit === state.temperatureUnit) return;
      state.temperatureUnit = button.dataset.tempUnit;
      window.localStorage.setItem("gardenLab.temperatureUnit", state.temperatureUnit);
      render();
    });
  });
}

function bindEvents() {
  els.actuatorGrid.addEventListener("click", handleActuatorAction);
  document.querySelector(".config-stack").addEventListener("click", handleConfigPower);
  [els.climateForm, els.lightForm, els.wateringForm, els.emergencyForm].forEach((form) => {
    form.addEventListener("submit", handleConfigSubmit);
  });
  bindSectionTabs();
  bindConfigAccordions();
  bindModeToggles();
  bindUtilityActions();
  bindRangePicker();
  window.addEventListener("resize", () => {
    syncSectionVisibility();
    redrawAllCharts();
    updateChartReadout();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest("canvas")) {
      if (state.inspect.locked) clearInspect();
    }
  });
}

function openRangePicker() {
  const sheet = document.getElementById("drum-sheet");
  const drum = document.getElementById("drum-scroll");
  drum.innerHTML = CHART_RANGE_OPTIONS
    .map((opt) => `<div class="drum-item" data-hours="${opt.hours}">${opt.label}</div>`)
    .join("");
  const idx = CHART_RANGE_OPTIONS.findIndex((o) => o.hours === state.chartHours);
  requestAnimationFrame(() => {
    drum.scrollTop = Math.max(0, idx * DRUM_ITEM_H);
    updateDrumHighlight(drum);
  });
  sheet.hidden = false;
}

function updateDrumHighlight(drum) {
  const idx = Math.max(0, Math.min(
    CHART_RANGE_OPTIONS.length - 1,
    Math.round(drum.scrollTop / DRUM_ITEM_H),
  ));
  drum.querySelectorAll(".drum-item").forEach((el, i) => el.classList.toggle("is-selected", i === idx));
}

function applyRangePicker() {
  const drum = document.getElementById("drum-scroll");
  const idx = Math.max(0, Math.min(
    CHART_RANGE_OPTIONS.length - 1,
    Math.round(drum.scrollTop / DRUM_ITEM_H),
  ));
  const opt = CHART_RANGE_OPTIONS[idx];
  document.getElementById("drum-sheet").hidden = true;
  if (opt.hours !== state.chartHours) {
    state.chartHours = opt.hours;
    window.localStorage.setItem("gardenLab.chartHours", String(opt.hours));
    document.getElementById("range-pill-label").textContent = opt.label;
    state.chartsData = null;
    state.historyData = null;
    loadGardenCharts().catch(() => {});
    loadGardenHistory().catch(() => {});
  }
}

function bindRangePicker() {
  const btn = document.getElementById("range-picker-btn");
  const sheet = document.getElementById("drum-sheet");
  const drum = document.getElementById("drum-scroll");
  const label = document.getElementById("range-pill-label");

  const currentOpt = CHART_RANGE_OPTIONS.find((o) => o.hours === state.chartHours) || CHART_RANGE_OPTIONS[2];
  label.textContent = currentOpt.label;

  btn.addEventListener("click", openRangePicker);
  sheet.querySelector(".drum-sheet__backdrop").addEventListener("click", applyRangePicker);
  sheet.querySelector(".drum-done-btn").addEventListener("click", applyRangePicker);

  let debounce;
  drum.addEventListener("scroll", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => updateDrumHighlight(drum), 60);
  });

  drum.addEventListener("click", (e) => {
    const item = e.target.closest(".drum-item");
    if (!item) return;
    const idx = CHART_RANGE_OPTIONS.findIndex((o) => String(o.hours) === item.dataset.hours);
    if (idx === -1) return;
    drum.scrollTo({ top: idx * DRUM_ITEM_H, behavior: "smooth" });
    setTimeout(() => applyRangePicker(), 250);
  });
}

bindEvents();
loadGardenState()
  .then(() => {
    setTimeout(() => loadGardenCharts().catch(() => {}), 200);
    setTimeout(() => loadGardenHistory().catch(() => {}), 600);
    setTimeout(() => loadGardenConfig().catch(() => {}), 1000);
  })
  .catch((error) => showToast(error.message, true));
setInterval(() => {
  loadGardenState().catch(() => {});
}, 5000);
setInterval(() => {
  loadGardenCharts().catch(() => {});
}, 30000);
setInterval(() => {
  loadGardenHistory().catch(() => {});
  loadGardenConfig().catch(() => {});
}, 45000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  loadGardenState().catch(() => {});
  loadGardenCharts().catch(() => {});
  loadGardenHistory().catch(() => {});
});
