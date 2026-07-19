const form = document.querySelector("#assessment-form");
const submitButton = form.querySelector("button[type='submit']");
const demoButton = document.querySelector("#demo-button");
const emptyState = document.querySelector("#empty-state");
const results = document.querySelector("#results");
const agentGrid = document.querySelector("#agent-grid");
const agentFlow = document.querySelector("#agent-flow");
const liveEvidence = document.querySelector("#live-evidence");
const evidenceQuality = document.querySelector("#evidence-quality");
const evidenceQualityList = document.querySelector("#evidence-quality-list");
const mapStatus = document.querySelector("#map-status");
const mapDetail = document.querySelector("#map-detail");
const scenarioStatus = document.querySelector("#scenario-status");
const commanderPanel = document.querySelector("#incident-commander");
const commanderStatus = document.querySelector("#commander-status");
const commanderSummary = document.querySelector("#commander-summary");
const commanderGaps = document.querySelector("#commander-gaps");
const reportDownload = document.querySelector("#report-download");
const workflowProgress = document.querySelector("#workflow-progress");
const workflowStatus = document.querySelector("#workflow-status");
const workflowProgressList = document.querySelector("#workflow-progress-list");
const riskExplanation = document.querySelector("#risk-explanation");
const scoreBreakdown = document.querySelector("#score-breakdown");
const positiveEvidence = document.querySelector("#positive-evidence");
const negativeEvidence = document.querySelector("#negative-evidence");
const confidenceRationale = document.querySelector("#confidence-rationale");
const missingData = document.querySelector("#missing-data");
const missingDataList = document.querySelector("#missing-data-list");
const themeToggle = document.querySelector("#theme-toggle");
const loadingState = document.querySelector("#loading-state");
const riskGauge = document.querySelector("#risk-gauge");
const riskGaugeSegments = document.querySelector("#risk-gauge-segments");
const assessmentTimeline = document.querySelector("#assessment-timeline");
const timelineSummary = document.querySelector("#timeline-summary");
const forecastOutlook = document.querySelector("#forecast-outlook");
const forecastTimeline = document.querySelector("#forecast-timeline");
const emergencyFeed = document.querySelector("#emergency-feed");
const feedRefresh = document.querySelector("#feed-refresh");
const verifiedAlerts = document.querySelector("#verified-alerts");
const assessmentNotices = document.querySelector("#assessment-notices");
const feedWarnings = document.querySelector("#feed-warnings");
const emergencyActionPlan = document.querySelector("#emergency-action-plan");
const actionPlanGrid = document.querySelector("#action-plan-grid");
const actionPlanLimits = document.querySelector("#action-plan-limits");
const bridgeAnalysisSection = document.querySelector("#bridge-analysis-section");
const bridgeAnalysisSummary = document.querySelector("#bridge-analysis-summary");
const bridgeAnalysisBody = document.querySelector("#bridge-analysis-body");
const bridgeDetailDialog = document.querySelector("#bridge-detail-dialog");
const bridgeDetailTitle = document.querySelector("#bridge-detail-title");
const bridgeDetailContent = document.querySelector("#bridge-detail-content");
const bridgeDetailClose = document.querySelector("#bridge-detail-close");
const findBridgesButton = document.querySelector("#find-bridges-button");
const bridgeLookupStatus = document.querySelector("#bridge-lookup-status");
const officialBridgePicker = document.querySelector("#official-bridge-picker");
const officialBridgeSelect = document.querySelector("#official-bridge-select");
const officialBridgeDetails = document.querySelector("#official-bridge-details");
let map;
let mapLayers;
let radarLayer;
let emergencyFeedTimer;
let bridgeAnalyses = [];
let bridgeSort = { key: "risk_level", direction: -1 };
let currentAssessment;
let officialBridgeCandidates = new Map();
const workflowItems = new Map();

function valueList(element, values) {
  element.replaceChildren(...values.map((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    return item;
  }));
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  themeToggle.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
  themeToggle.setAttribute("title", themeToggle.getAttribute("aria-label"));
  try {
    localStorage.setItem("aegis-theme", theme);
  } catch (_) {
    // Theme choice is optional and should not interrupt incident work.
  }
}

function setStatusCard(cardId, value, detail, state) {
  const valueElement = document.querySelector(`#${cardId}-value`);
  const detailElement = document.querySelector(`#${cardId}-detail`);
  const card = valueElement.closest(".status-card");
  valueElement.textContent = value;
  detailElement.textContent = detail;
  card.className = `status-card is-${state}`;
}

function resetOfficialBridgeSelection(message = "Search a location, then select an official bridge record.") {
  officialBridgeCandidates = new Map();
  officialBridgeSelect.replaceChildren(new Option("Choose an FHWA National Bridge Inventory record", ""));
  officialBridgePicker.hidden = true;
  officialBridgeDetails.replaceChildren();
  officialBridgeDetails.hidden = true;
  form.elements.official_bridge_id.value = "";
  form.elements.asset_name.readOnly = false;
  form.elements.condition_score.readOnly = false;
  form.elements.asset_age_years.readOnly = false;
  bridgeLookupStatus.textContent = message;
}

function renderOfficialBridgeDetails(bridge) {
  const values = [
    ["Source", "FHWA National Bridge Inventory"],
    ["Location", bridge.location_description || "Not provided by the inventory"],
    ["Route", bridge.route || "Not provided by the inventory"],
    ["Year built", bridge.year_built ?? "Not provided"],
    ["Condition score", bridge.condition_score === null ? "No usable component-condition code" : `${bridge.condition_score}/100 (normalized from NBI codes)`],
    ["Traffic", bridge.average_daily_traffic === null ? "Not provided" : `${bridge.average_daily_traffic.toLocaleString()} vehicles/day${bridge.traffic_year ? ` (${bridge.traffic_year})` : ""}`],
    ["Last inspection", bridge.last_inspection_date || "Not provided"],
  ];
  const list = document.createElement("dl");
  values.forEach(([label, value]) => {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = String(value);
    row.append(term, description);
    list.append(row);
  });
  const limits = document.createElement("p");
  limits.className = "official-bridge-limits";
  limits.textContent = bridge.limitations.join(" ");
  officialBridgeDetails.replaceChildren(list, limits);
  officialBridgeDetails.hidden = false;
}

function selectOfficialBridge() {
  const bridge = officialBridgeCandidates.get(officialBridgeSelect.value);
  if (!bridge) {
    form.elements.official_bridge_id.value = "";
    officialBridgeDetails.replaceChildren();
    officialBridgeDetails.hidden = true;
    form.elements.asset_name.readOnly = false;
    form.elements.condition_score.readOnly = false;
    form.elements.asset_age_years.readOnly = false;
    bridgeLookupStatus.textContent = "Choose an official bridge record, or enter verified manual inputs.";
    return;
  }
  form.elements.official_bridge_id.value = bridge.nbi_record_id;
  form.elements.asset_name.value = bridge.name;
  form.elements.asset_name.readOnly = true;
  if (bridge.condition_score !== null) {
    form.elements.condition_score.value = bridge.condition_score;
    form.elements.condition_score.readOnly = true;
  } else {
    form.elements.condition_score.value = "";
    form.elements.condition_score.readOnly = false;
  }
  if (bridge.year_built !== null) {
    form.elements.asset_age_years.value = Math.max(0, new Date().getUTCFullYear() - bridge.year_built);
    form.elements.asset_age_years.readOnly = true;
  } else {
    form.elements.asset_age_years.value = "";
    form.elements.asset_age_years.readOnly = false;
  }
  bridgeLookupStatus.textContent = `Official FHWA bridge record selected: ${bridge.name}. Aegis will verify it again on the server.`;
  renderOfficialBridgeDetails(bridge);
}

async function findOfficialBridges() {
  const location = form.elements.location.value.trim();
  if (location.length < 3) {
    bridgeLookupStatus.textContent = "Enter a U.S. city, state, or ZIP code first.";
    return;
  }
  findBridgesButton.disabled = true;
  bridgeLookupStatus.textContent = "Searching the official FHWA bridge inventory.";
  try {
    const response = await fetch(`/api/bridges?${new URLSearchParams({ location })}`);
    if (!response.ok) throw new Error("The official bridge inventory did not respond.");
    const result = await response.json();
    officialBridgeCandidates = new Map(result.bridges.map((bridge) => [bridge.nbi_record_id, bridge]));
    officialBridgeSelect.replaceChildren(new Option("Choose an FHWA National Bridge Inventory record", ""));
    result.bridges.forEach((bridge) => {
      const route = bridge.route ? ` | ${bridge.route}` : "";
      const built = bridge.year_built ? ` | built ${bridge.year_built}` : "";
      officialBridgeSelect.add(new Option(`${bridge.name}${route}${built}`, bridge.nbi_record_id));
    });
    officialBridgePicker.hidden = !result.bridges.length;
    officialBridgeDetails.replaceChildren();
    officialBridgeDetails.hidden = true;
    form.elements.official_bridge_id.value = "";
    bridgeLookupStatus.textContent = result.bridges.length
      ? `${result.bridges.length} official bridge record${result.bridges.length === 1 ? "" : "s"} found near ${result.location}.`
      : (result.warnings || ["No official bridge records were found."]).join(" ");
  } catch (error) {
    resetOfficialBridgeSelection(error instanceof Error ? error.message : "Official bridge lookup failed.");
  } finally {
    findBridgesButton.disabled = false;
  }
}

function renderLoadingState(isLoading) {
  loadingState.hidden = !isLoading;
}

function renderRiskGauge(risk) {
  const activeSegments = Math.max(0, Math.min(10, Math.ceil(risk.score / 10)));
  riskGauge.dataset.level = risk.risk_level.toLowerCase();
  riskGaugeSegments.replaceChildren(...Array.from({ length: 10 }, (_, index) => {
    const segment = document.createElement("span");
    if (index < activeSegments) segment.className = "active";
    return segment;
  }));
}

function renderTimeline(findings) {
  const completed = findings.filter((finding) => finding.status === "complete").length;
  const degraded = findings.filter((finding) => finding.status === "degraded").length;
  timelineSummary.textContent = degraded ? `${completed} complete, ${degraded} degraded` : `${completed} agents complete`;
  assessmentTimeline.replaceChildren(...findings.map((finding, index) => {
    const item = document.createElement("li");
    item.className = finding.status;
    const marker = document.createElement("span");
    marker.className = "timeline-marker";
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = finding.agent;
    const detail = document.createElement("span");
    detail.textContent = finding.summary;
    const timing = document.createElement("time");
    timing.textContent = finding.duration_ms === null || finding.duration_ms === undefined ? finding.status : `${finding.duration_ms} ms`;
    content.append(title, detail);
    item.append(marker, content, timing);
    item.style.animationDelay = `${Math.min(index * 55, 300)}ms`;
    return item;
  }));
}

function renderForecastTimeline(entries, live) {
  if (!entries?.length) {
    forecastOutlook.hidden = true;
    return;
  }
  const labels = sourceLabels(live);
  const categories = [
    ["Weather", "weather"],
    ["River level", "river_level"],
    ["Flood risk", "flood_risk"],
    ["Bridge status", "bridge_status"],
    ["Recommended action", "recommended_action"],
  ];
  forecastTimeline.replaceChildren(...entries.map((entry, index) => {
    const item = document.createElement("li");
    item.className = entry.kind;
    item.style.animationDelay = `${Math.min(index * 70, 280)}ms`;
    const header = document.createElement("header");
    const time = document.createElement("time");
    time.textContent = entry.label;
    const kind = document.createElement("span");
    kind.textContent = entry.kind;
    header.append(time, kind);
    const facts = document.createElement("dl");
    categories.forEach(([label, property]) => {
      const statement = entry[property];
      const row = document.createElement("div");
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      const text = document.createElement("span");
      text.textContent = statement.text;
      const citation = document.createElement("small");
      citation.textContent = `Sources: ${statement.source_ids.map((id) => labels[id] || id).join(", ")}`;
      description.append(text, citation);
      row.append(term, description);
      facts.append(row);
    });
    item.append(header, facts);
    if (entry.limitations?.length) {
      const limits = document.createElement("p");
      limits.className = "forecast-limits";
      limits.textContent = `Limits: ${entry.limitations.join(" ")}`;
      item.append(limits);
    }
    return item;
  }));
  forecastOutlook.hidden = false;
}

function renderActionPlan(plan, live) {
  if (!plan) {
    emergencyActionPlan.hidden = true;
    return;
  }
  const labels = sourceLabels(live);
  const sections = [
    plan.immediate_actions,
    plan.plan_30_minutes,
    plan.plan_2_hours,
    plan.plan_12_hours,
    plan.public_communication,
    plan.inspection_priorities,
    plan.resource_deployment,
  ];
  actionPlanGrid.replaceChildren(...sections.map((section) => {
    const item = document.createElement("article");
    item.className = "action-plan-section";
    const title = document.createElement("h4");
    title.textContent = section.title;
    const observationTitle = document.createElement("h5");
    observationTitle.textContent = "Observed evidence";
    const observations = document.createElement("ul");
    observations.className = "cited-list";
    citedList(observations, section.observations || [], labels);
    const recommendationTitle = document.createElement("h5");
    recommendationTitle.textContent = "Recommended action";
    const recommendations = document.createElement("ul");
    recommendations.className = "cited-list recommendations";
    citedList(recommendations, section.recommendations || [], labels);
    item.append(title, observationTitle, observations, recommendationTitle, recommendations);
    if (section.limitations?.length) {
      const limits = document.createElement("p");
      limits.className = "plan-section-limits";
      limits.textContent = `Limit: ${section.limitations.join(" ")}`;
      item.append(limits);
    }
    return item;
  }));
  actionPlanLimits.textContent = plan.limitations.join(" ");
  actionPlanLimits.hidden = !plan.limitations.length;
  emergencyActionPlan.hidden = false;
}

function formatFeedTime(value) {
  if (!value) return "Time not supplied by source";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString();
}

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch (_) {
    return null;
  }
}

function renderAssessmentNotices(data) {
  const notices = [
    {
      label: "Risk assessment",
      text: `Aegis assesses ${data.asset.name} as ${data.risk.risk_level} risk (${data.risk.score}/100). This is decision support, not a verified public alert.`,
    },
    {
      label: "24-hour outlook",
      text: data.timeline?.find((entry) => entry.hours_ahead === 24)?.flood_risk?.text || "No 24-hour Aegis outlook was available.",
    },
  ];
  assessmentNotices.replaceChildren(...notices.map((notice) => {
    const item = document.createElement("article");
    item.className = "assessment-notice";
    const label = document.createElement("strong");
    label.textContent = notice.label;
    const text = document.createElement("p");
    text.textContent = notice.text;
    const source = document.createElement("small");
    source.textContent = "Source: Aegis risk model and cited assessment evidence";
    item.append(label, text, source);
    return item;
  }));
}

function renderEmergencyFeed(feed, data) {
  feedRefresh.textContent = `Last refreshed ${formatFeedTime(feed.refreshed_at)}`;
  verifiedAlerts.replaceChildren(...feed.alerts.map((alert) => {
    const item = document.createElement("article");
    item.className = `feed-alert ${alert.category}`;
    const header = document.createElement("header");
    const category = document.createElement("span");
    category.textContent = alert.category;
    const severity = document.createElement("span");
    severity.textContent = alert.severity || "Advisory";
    header.append(category, severity);
    const title = document.createElement("h5");
    title.textContent = alert.title;
    const summary = document.createElement("p");
    summary.textContent = alert.summary;
    const sourceUrl = safeExternalUrl(alert.source_url);
    const source = document.createElement(sourceUrl ? "a" : "span");
    source.className = "feed-source";
    source.textContent = `${alert.source_name} | ${formatFeedTime(alert.observed_at)}`;
    if (sourceUrl) {
      source.href = sourceUrl;
      source.target = "_blank";
      source.rel = "noreferrer";
    }
    item.append(header, title, summary, source);
    return item;
  }));
  if (!feed.alerts.length) {
    const empty = document.createElement("p");
    empty.className = "feed-empty";
    empty.textContent = "No verified public alerts were returned for this location during this refresh.";
    verifiedAlerts.append(empty);
  }
  renderAssessmentNotices(data);
  feedWarnings.textContent = feed.warnings.join(" ");
  feedWarnings.hidden = !feed.warnings.length;
  emergencyFeed.hidden = false;
}

async function refreshEmergencyFeed(data) {
  clearTimeout(emergencyFeedTimer);
  const live = data.live_intelligence;
  if (!live?.coordinates) {
    emergencyFeed.hidden = true;
    return;
  }
  feedRefresh.textContent = "Refreshing verified sources";
  emergencyFeed.hidden = false;
  try {
    const query = new URLSearchParams({
      latitude: String(live.coordinates.latitude),
      longitude: String(live.coordinates.longitude),
      location: live.resolved_location || data.asset.location,
    });
    const response = await fetch(`/api/emergency-feed?${query}`);
    if (!response.ok) throw new Error("Verified alert sources did not respond.");
    renderEmergencyFeed(await response.json(), data);
  } catch (error) {
    verifiedAlerts.replaceChildren();
    const unavailable = document.createElement("p");
    unavailable.className = "feed-empty";
    unavailable.textContent = "Verified alert sources are temporarily unavailable.";
    verifiedAlerts.append(unavailable);
    renderAssessmentNotices(data);
    feedWarnings.textContent = error instanceof Error ? error.message : "The alert feed could not be refreshed.";
    feedWarnings.hidden = false;
  } finally {
    emergencyFeedTimer = setTimeout(() => refreshEmergencyFeed(data), 60_000);
  }
}

function renderOperationalStatus(data) {
  const live = data.live_intelligence;
  const completed = data.findings.filter((finding) => finding.status === "complete").length;
  const degraded = data.findings.filter((finding) => finding.status === "degraded").length;
  const sourceCount = live?.sources?.length || 0;
  setStatusCard("coverage", sourceCount ? `${sourceCount} sources` : "Manual inputs", sourceCount ? "Public evidence snapshot recorded" : "No live source snapshot returned", sourceCount ? "ready" : "degraded");
  setStatusCard("agents", `${completed}/${data.findings.length} complete`, degraded ? `${degraded} agent output(s) degraded` : "Specialist workflow completed", degraded ? "degraded" : "ready");
  setStatusCard("assessment", data.risk.risk_level, `Risk score ${data.risk.score}/100`, data.risk.risk_level.toLowerCase());
}

function bridgeRank(value) {
  return { LOW: 1, MODERATE: 2, HIGH: 3, CRITICAL: 4 }[value] || 0;
}

function sortedBridgeAnalyses() {
  return [...bridgeAnalyses].sort((first, second) => {
    const firstValue = bridgeSort.key === "risk_level" || bridgeSort.key === "importance" || bridgeSort.key === "traffic_impact"
      ? bridgeRank(first[bridgeSort.key])
      : first[bridgeSort.key];
    const secondValue = bridgeSort.key === "risk_level" || bridgeSort.key === "importance" || bridgeSort.key === "traffic_impact"
      ? bridgeRank(second[bridgeSort.key])
      : second[bridgeSort.key];
    if (typeof firstValue === "string") return firstValue.localeCompare(secondValue) * bridgeSort.direction;
    return (firstValue - secondValue) * bridgeSort.direction;
  });
}

function bridgeBadge(text, style) {
  const badge = document.createElement("span");
  badge.className = `bridge-badge ${style}`;
  badge.textContent = text;
  return badge;
}

function renderBridgeTable() {
  bridgeAnalysisBody.replaceChildren(...sortedBridgeAnalyses().map((bridge) => {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.scope = "row";
    const title = document.createElement("strong");
    title.textContent = bridge.name;
    const scope = document.createElement("small");
    scope.textContent = bridge.risk_scope === "full_assessment" ? "Full assessment" : "Flood exposure";
    name.append(title, scope);
    const risk = document.createElement("td");
    risk.append(bridgeBadge(bridge.risk_level, bridge.risk_level.toLowerCase()));
    const importance = document.createElement("td");
    importance.append(bridgeBadge(bridge.importance, bridge.importance.toLowerCase()));
    const distance = document.createElement("td");
    distance.textContent = `${bridge.distance_km.toFixed(1)} km`;
    const hospitals = document.createElement("td");
    hospitals.textContent = String(bridge.nearby_hospitals);
    const schools = document.createElement("td");
    schools.textContent = String(bridge.nearby_schools);
    const traffic = document.createElement("td");
    traffic.append(bridgeBadge(bridge.traffic_impact, bridge.traffic_impact.toLowerCase()));
    const alternatives = document.createElement("td");
    alternatives.textContent = String(bridge.alternative_crossings);
    const detail = document.createElement("td");
    const inspect = document.createElement("button");
    inspect.type = "button";
    inspect.className = "table-inspect";
    inspect.textContent = "Inspect";
    inspect.addEventListener("click", () => openBridgeDetails(bridge.bridge_id));
    detail.append(inspect);
    row.append(name, risk, importance, distance, hospitals, schools, traffic, alternatives, detail);
    return row;
  }));
  document.querySelectorAll("[data-bridge-sort]").forEach((button) => {
    const key = button.dataset.bridgeSort;
    button.setAttribute("aria-sort", key === bridgeSort.key ? (bridgeSort.direction === 1 ? "ascending" : "descending") : "none");
  });
}

function openBridgeDetails(bridgeId) {
  const bridge = bridgeAnalyses.find((item) => item.bridge_id === bridgeId);
  if (!bridge) return;
  bridgeDetailTitle.textContent = bridge.name;
  const labels = sourceLabels(currentAssessment?.live_intelligence);
  const facts = [
    ["Exposure risk", `${bridge.risk_level} (${bridge.risk_scope.replace("_", " ")})`],
    ["Risk basis", bridge.risk_basis],
    ["Importance", bridge.importance_basis],
    ["Traffic impact", bridge.traffic_impact_basis],
    ["Distance", `${bridge.distance_km.toFixed(1)} km from assessed bridge`],
    ["Sources", bridge.source_ids.map((id) => labels[id] || id).join(", ")],
  ];
  const list = document.createElement("dl");
  facts.forEach(([label, value]) => {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    row.append(term, description);
    list.append(row);
  });
  bridgeDetailContent.replaceChildren(list);
  if (bridge.limitations.length) {
    const limits = document.createElement("p");
    limits.className = "bridge-detail-limits";
    limits.textContent = `Limits: ${bridge.limitations.join(" ")}`;
    bridgeDetailContent.append(limits);
  }
  if (typeof bridgeDetailDialog.showModal === "function" && !bridgeDetailDialog.open) bridgeDetailDialog.showModal();
  else bridgeDetailDialog.setAttribute("open", "");
}

function renderBridgeAnalysis(analyses, live) {
  bridgeAnalyses = analyses || [];
  if (!bridgeAnalyses.length) {
    bridgeAnalysisSection.hidden = true;
    return;
  }
  bridgeAnalysisSummary.textContent = `${bridgeAnalyses.length} mapped bridge${bridgeAnalyses.length === 1 ? "" : "es"}`;
  bridgeAnalysisSection.hidden = false;
  renderBridgeTable(live);
}

function resetWorkflowProgress() {
  workflowItems.clear();
  workflowProgressList.replaceChildren();
  workflowProgress.hidden = false;
  workflowStatus.textContent = "Starting";
  renderLoadingState(true);
  setStatusCard("coverage", "Collecting", "Retrieving public evidence", "running");
  setStatusCard("agents", "Starting", "Specialist agents initializing", "running");
  setStatusCard("assessment", "In progress", "No risk decision yet", "running");
}

function renderWorkflowProgress(progress) {
  workflowProgress.hidden = false;
  workflowStatus.textContent = progress.status === "complete" ? "Complete" : "Running";
  let item = workflowItems.get(progress.agent);
  if (!item) {
    item = document.createElement("li");
    const name = document.createElement("strong");
    const message = document.createElement("span");
    const timing = document.createElement("time");
    item.append(name, message, timing);
    workflowItems.set(progress.agent, item);
    workflowProgressList.append(item);
  }
  item.className = progress.status;
  item.querySelector("strong").textContent = progress.agent;
  item.querySelector("span").textContent = progress.message;
  item.querySelector("time").textContent = progress.duration_ms === null || progress.duration_ms === undefined ? progress.status : `${progress.duration_ms} ms`;
  if (progress.status === "running") setStatusCard("agents", "Running", progress.message, "running");
}

async function runStreamedAssessment(payload) {
  const response = await fetch("/api/assessments/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) throw new Error("Check the entered values and try again.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assessment;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    lines.filter(Boolean).forEach((line) => {
      const event = JSON.parse(line);
      if (event.type === "progress") renderWorkflowProgress(event.progress);
      if (event.type === "result") assessment = event.assessment;
      if (event.type === "error") throw new Error(event.message);
    });
  }
  if (!assessment) throw new Error("The assessment stream ended before returning a result.");
  return assessment;
}

function sourceLabels(live) {
  const labels = {
    "operator-field-report": "Operator field report",
    "operator-assessment-inputs": "Operator assessment inputs",
    "aegis-risk-model": "Aegis risk model",
  };
  (live?.sources || []).forEach((source) => {
    labels[source.id] = source.provider || source.label || source.id;
  });
  return labels;
}

function citedList(element, statements, labels) {
  element.replaceChildren(...statements.map((statement) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = statement.text;
    const citation = document.createElement("span");
    citation.className = "citation";
    citation.textContent = `Sources: ${statement.source_ids.map((id) => labels[id] || id).join(", ")}`;
    item.append(text, citation);
    return item;
  }));
}

function renderExplainability(explanation, live, confidence) {
  if (!explanation) {
    riskExplanation.hidden = true;
    return;
  }
  const labels = sourceLabels(live);
  const signalLabels = {
    "Weather and water": "Flood conditions",
    "Structural vulnerability": "Infrastructure condition & age",
    "Emergency access": "Emergency access & route impact",
  };
  const signals = (explanation.score_components || []).map((component) => ({
    ...component,
    label: signalLabels[component.label] || component.label,
    percentage: Math.min(100, Math.round((component.points / component.max_points) * 100)),
  }));
  signals.push({
    label: "Data confidence",
    points: confidence,
    max_points: 100,
    percentage: confidence,
    explanation: "Confidence reflects the available evidence and model limits; it is not a probability of bridge failure.",
    source_ids: ["aegis-risk-model", "operator-assessment-inputs"],
  });
  scoreBreakdown.replaceChildren(...signals.map((component) => {
    const row = document.createElement("article");
    row.className = "score-component";
    const header = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = component.label;
    const points = document.createElement("span");
    points.textContent = `${component.percentage}%`;
    header.append(label, points);
    const track = document.createElement("div");
    track.className = "score-track";
    const fill = document.createElement("span");
    fill.style.width = `${component.percentage}%`;
    track.append(fill);
    const detail = document.createElement("p");
    detail.textContent = component.explanation;
    const citation = document.createElement("span");
    citation.className = "citation";
    citation.textContent = `Sources: ${component.source_ids.map((id) => labels[id] || id).join(", ")}`;
    row.append(header, track, detail, citation);
    return row;
  }));
  citedList(positiveEvidence, explanation.positive_evidence || [], labels);
  citedList(negativeEvidence, explanation.negative_evidence || [], labels);
  positiveEvidence.closest("div").hidden = !positiveEvidence.children.length;
  negativeEvidence.closest("div").hidden = !negativeEvidence.children.length;
  confidenceRationale.replaceChildren();
  if (explanation.confidence_rationale) {
    const confidenceList = document.createElement("ul");
    confidenceList.className = "cited-list";
    confidenceRationale.append(confidenceList);
    citedList(confidenceList, [explanation.confidence_rationale], labels);
  }
  valueList(missingDataList, explanation.missing_data || []);
  missingData.hidden = !(explanation.missing_data || []).length;
  riskExplanation.hidden = false;
}

function renderCommander(commander, live) {
  if (!commander) {
    commanderPanel.hidden = true;
    return;
  }
  const labels = sourceLabels(live);
  commanderPanel.hidden = false;
  commanderStatus.textContent = commander.available ? "Groq evidence synthesis" : "Deterministic fallback";
  commanderSummary.textContent = commander.executive_summary;
  citedList(document.querySelector("#commander-reasoning"), commander.reasoning || [], labels);
  citedList(document.querySelector("#commander-priorities"), commander.immediate_priorities || [], labels);
  citedList(document.querySelector("#commander-actions"), commander.recommended_actions || [], labels);
  citedList(document.querySelector("#commander-long-term"), commander.long_term_recommendations || [], labels);
  const gaps = [...(commander.data_gaps || []), ...(commander.warning ? [commander.warning] : [])];
  commanderGaps.textContent = gaps.length ? `Data gaps and limits: ${gaps.join(" ")}` : "";
  commanderGaps.hidden = !gaps.length;
}

function renderFindings(findings) {
  renderAgentFlow(findings);
  agentGrid.replaceChildren(...findings.map((finding) => {
    const card = document.createElement("article");
    card.className = "agent-card";
    const title = document.createElement("h3");
    title.textContent = finding.agent;
    const status = document.createElement("span");
    status.textContent = finding.status.replaceAll("_", " ");
    const summary = document.createElement("p");
    summary.textContent = finding.summary;
    const duration = document.createElement("time");
    duration.textContent = finding.duration_ms === null || finding.duration_ms === undefined ? "No runtime reported" : `${finding.duration_ms} ms`;
    card.append(title, status, summary, duration);
    return card;
  }));
}

function renderAgentFlow(findings) {
  const statuses = new Map(findings.map((finding) => [finding.agent, finding.status]));
  const evidenceAgents = ["Weather Agent", "Flood Agent", "Infrastructure Agent", "Routing Agent"];
  const makeNode = (name, detail = "") => {
    const node = document.createElement("div");
    node.className = `agent-flow-node ${statuses.get(name) || "pending"}`;
    const title = document.createElement("strong");
    title.textContent = name;
    node.append(title);
    if (detail) {
      const description = document.createElement("span");
      description.textContent = detail;
      node.append(description);
    }
    return node;
  };
  const arrow = document.createElement("span");
  arrow.className = "agent-flow-arrow";
  arrow.setAttribute("aria-hidden", "true");
  arrow.textContent = "↓";

  const evidenceRow = document.createElement("div");
  evidenceRow.className = "agent-flow-evidence";
  evidenceRow.append(...evidenceAgents.map((name) => makeNode(name)));
  const coordinator = makeNode("Coordinator Agent", "Deterministic risk assessment");
  const planning = makeNode("Emergency Planning Agent", "Reviewable operational guidance");
  const commander = makeNode("AI Incident Commander", "Evidence-backed brief; cannot change risk");
  const human = makeNode("Qualified Human Review", "Approves any operational action");
  human.classList.add("human");

  agentFlow.replaceChildren(evidenceRow, arrow.cloneNode(true), coordinator, arrow.cloneNode(true), planning, arrow.cloneNode(true), commander, arrow.cloneNode(true), human);
}

function ensureMap() {
  if (map || !window.L) return;
  map = window.L.map("map", { scrollWheelZoom: false }).setView([42.6526, -73.7562], 11);
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);
  mapLayers = window.L.featureGroup().addTo(map);
}

function point(coordinates) {
  return [coordinates.latitude, coordinates.longitude];
}

function markerPopup(title, details) {
  const wrapper = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  const description = document.createElement("div");
  description.textContent = details;
  wrapper.append(heading, description);
  return wrapper;
}

function clearMapEvidence() {
  if (mapLayers) mapLayers.clearLayers();
  if (radarLayer && map) {
    map.removeLayer(radarLayer);
    radarLayer = undefined;
  }
}

function renderMap(live, risk) {
  ensureMap();
  if (!map || !live?.coordinates) {
    clearMapEvidence();
    mapStatus.textContent = "Live map data unavailable; manual assessment still completed";
    mapDetail.textContent = live?.warnings?.join(" ") || "No resolved map location was returned.";
    return;
  }
  clearMapEvidence();
  if (live.radar_layer?.tile_url) {
    radarLayer = window.L.tileLayer(live.radar_layer.tile_url, {
      attribution: live.radar_layer.attribution,
      opacity: 0.52,
      zIndex: 350,
    }).addTo(map);
  }
  const bounds = [];
  const assets = live.bridge_assets || [];
  assets.forEach((asset, index) => {
    const assetPoint = point(asset.coordinates);
    bounds.push(assetPoint);
    const isAssessedAsset = index === 0;
    const color = isAssessedAsset ? (risk.risk_level === "CRITICAL" ? "#b64a31" : "#c48a24") : "#006e68";
    const marker = window.L.circleMarker(assetPoint, { className: isAssessedAsset ? "risk-marker-pulse" : "", color, fillColor: color, fillOpacity: 0.82, radius: isAssessedAsset ? 10 : 6, weight: 2 });
    marker.bindPopup(markerPopup(asset.name, `${asset.source}${asset.risk_level ? ` | ${asset.risk_level} risk` : ""}`));
    marker.addTo(mapLayers);
  });
  if (live.flood_screening) {
    const screening = live.flood_screening;
    const circle = window.L.circle(point(screening.center), { className: "flood-zone-pulse", color: "#3274a1", fillColor: "#3274a1", fillOpacity: 0.12, radius: screening.radius_meters, weight: 2 });
    circle.bindPopup(markerPopup(`${screening.classification} flood-risk screening area`, screening.disclaimer));
    circle.addTo(mapLayers);
    bounds.push(circle.getBounds().getNorthEast(), circle.getBounds().getSouthWest());
  }
  if (live.nearest_gauge) {
    const gauge = live.nearest_gauge;
    const label = gauge.stage_ft !== null ? `Stage ${gauge.stage_ft.toFixed(2)} ft` : `Flow ${gauge.flow_cfs?.toFixed(0) || "unknown"} cfs`;
    const gaugeMarker = window.L.circleMarker(point(gauge.coordinates), { color: "#294c60", fillColor: "#edf2f0", fillOpacity: 1, radius: 7, weight: 3 });
    gaugeMarker.bindPopup(markerPopup(gauge.site_name, `USGS gauge | ${label}`));
    gaugeMarker.addTo(mapLayers);
    bounds.push(point(gauge.coordinates));
  }
  (live.critical_infrastructure || []).forEach((facility) => {
    const colors = { hospital: "#a64040", "fire station": "#d36b2e", police: "#3d5f8d", school: "#746146" };
    const color = colors[facility.category] || "#52666b";
    const facilityMarker = window.L.circleMarker(point(facility.coordinates), { color, fillColor: color, fillOpacity: 0.8, radius: 5, weight: 2 });
    facilityMarker.bindPopup(markerPopup(facility.name, `${facility.category} | ${facility.source}`));
    facilityMarker.addTo(mapLayers);
    bounds.push(point(facility.coordinates));
  });
  (live.seismic_events || []).forEach((event) => {
    const eventPoint = point(event.coordinates);
    const seismicMarker = window.L.circleMarker(eventPoint, { color: "#6f5a99", fillColor: "#6f5a99", fillOpacity: 0.7, radius: 5, weight: 2 });
    seismicMarker.bindPopup(markerPopup(`M${event.magnitude.toFixed(1)} earthquake`, `${event.place} | ${event.occurred_at}`));
    seismicMarker.addTo(mapLayers);
  });
  if (live.alternate_route?.geometry?.length > 1) {
    const routePoints = live.alternate_route.geometry.map(point);
    const route = window.L.polyline(routePoints, { className: "route-flow", color: "#6f5a99", weight: 4, opacity: 0.85 });
    route.bindPopup(markerPopup(live.alternate_route.label, `${live.alternate_route.distance_km} km | approx. ${live.alternate_route.duration_minutes} min | planning only`));
    route.addTo(mapLayers);
    bounds.push(...routePoints);
  }
  if (bounds.length) map.fitBounds(window.L.latLngBounds(bounds), { padding: [28, 28], maxZoom: 14 });
  mapStatus.textContent = live.enabled ? "Live public-source map layers loaded" : "Scenario map layers loaded";
  const sourceText = live.sources?.length ? `Sources: ${live.sources.map((source) => source.provider).join(", ")}.` : "";
  const warningText = live.warnings?.length ? ` ${live.warnings.join(" ")}` : "";
  mapDetail.textContent = `${sourceText}${warningText}`;
}

function renderLiveEvidence(live, isDemo, officialBridge) {
  if (!live) {
    liveEvidence.hidden = true;
    return;
  }
  const facts = [];
  if (officialBridge) {
    facts.push(`Official FHWA bridge record: ${officialBridge.name}${officialBridge.year_built ? `, built ${officialBridge.year_built}` : ""}${officialBridge.last_inspection_date ? `, inspection date ${officialBridge.last_inspection_date}` : ""}.`);
  }
  if (live.weather) facts.push(`Live forecast: ${live.weather.precipitation_next_24h_mm} mm precipitation and ${live.weather.wind_gust_kph} km/h peak gusts in the next 24 hours.`);
  if (live.flood_forecast) facts.push(`Modelled river discharge: ${live.flood_forecast.river_discharge_m3s} m3/s, with a ${live.flood_forecast.peak_7day_discharge_m3s} m3/s seven-day peak.`);
  if (live.nearest_gauge) {
    const value = live.nearest_gauge.stage_ft !== null ? `${live.nearest_gauge.stage_ft.toFixed(2)} ft stage` : `${live.nearest_gauge.flow_cfs?.toFixed(0) || "unknown"} cfs flow`;
    facts.push(`Nearest gauge: ${live.nearest_gauge.site_name} at ${value}.`);
  }
  if (live.weather_alerts?.length) facts.push(`Official NWS alerts: ${live.weather_alerts.map((alert) => alert.event).join(", ")}.`);
  if (live.seismic_events?.length) facts.push(`Recent USGS earthquakes within 100 km: ${live.seismic_events.length}.`);
  if (live.terrain) facts.push(`Asset elevation: ${live.terrain.elevation_meters} m (screening context only).`);
  if (live.critical_infrastructure?.length) facts.push(`Mapped critical facilities: ${live.critical_infrastructure.length}.`);
  if (live.radar_layer?.observed_at) facts.push(`RainViewer radar frame: ${new Date(live.radar_layer.observed_at).toLocaleString()}.`);
  if (isDemo) facts.unshift("Competition scenario: risk inputs are simulated and should not be treated as live emergency information.");
  facts.push(...(live.warnings || []));
  liveEvidence.textContent = facts.join(" ") || "Live sources did not return evidence; manual inputs were used.";
  liveEvidence.hidden = false;
}

function renderEvidenceQuality(live, officialBridge) {
  const availableSources = new Set((live?.sources || []).map((source) => source.id));
  const sources = [
    {
      label: "FHWA bridge data",
      available: Boolean(officialBridge),
      stars: 5,
      detail: "Official bridge inventory record; not a real-time structural sensor feed.",
    },
    {
      label: "Weather forecast",
      available: availableSources.has("open-meteo-weather"),
      stars: 5,
      detail: "Public meteorological forecast used as operational context.",
    },
    {
      label: "River gauge",
      available: availableSources.has("usgs-water"),
      stars: 4,
      detail: "USGS observed gauge data; local bridge thresholds still require engineering validation.",
    },
    {
      label: "Satellite data",
      available: false,
      stars: 0,
      detail: "Not available in the current MVP.",
    },
  ];
  evidenceQualityList.replaceChildren(...sources.map((source) => {
    const row = document.createElement("article");
    row.className = `evidence-quality-row ${source.available ? "available" : "unavailable"}`;
    const heading = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = source.label;
    const rating = document.createElement("span");
    rating.className = "source-rating";
    rating.setAttribute("aria-label", source.available ? `${source.stars} out of 5 baseline source-reliability stars` : "Not available for this assessment");
    rating.textContent = source.available ? "★".repeat(source.stars) + "☆".repeat(5 - source.stars) : "Not available";
    heading.append(name, rating);
    const detail = document.createElement("p");
    detail.textContent = source.detail;
    row.append(heading, detail);
    return row;
  }));
  evidenceQuality.hidden = false;
}

function renderAssessment(data) {
  emptyState.hidden = true;
  results.hidden = false;
  renderLoadingState(false);
  document.querySelector("#risk-level").textContent = data.risk.risk_level;
  document.querySelector("#risk-score").textContent = data.risk.score;
  const enrichment = data.narrative_enriched ? "Groq writing enhancement active" : "deterministic writing fallback";
  document.querySelector("#risk-confidence").textContent = `Model confidence: ${data.risk.confidence}% - ${enrichment} - human review required`;
  renderRiskGauge(data.risk);
  const labels = sourceLabels(data.live_intelligence);
  const explainedReasons = data.risk.explanation?.positive_evidence || [];
  citedList(
    document.querySelector("#reasons"),
    explainedReasons.length ? explainedReasons : data.risk.reasons.map((text) => ({ text, source_ids: ["aegis-risk-model"] })),
    labels,
  );
  citedList(
    document.querySelector("#actions"),
    data.risk.recommended_actions.map((text) => ({ text, source_ids: ["aegis-risk-model"] })),
    labels,
  );
  document.querySelector("#alert-draft").textContent = data.public_alert_draft;
  document.querySelector("#situation-report").textContent = data.situation_report;
  reportDownload.hidden = !data.report_url;
  if (data.report_url) reportDownload.href = data.report_url;
  renderExplainability(data.risk.explanation, data.live_intelligence, data.risk.confidence);
  renderLiveEvidence(data.live_intelligence, data.demo_scenario, data.official_bridge);
  renderEvidenceQuality(data.live_intelligence, data.official_bridge);
  renderCommander(data.incident_commander, data.live_intelligence);
  renderFindings(data.findings);
  renderTimeline(data.findings);
  renderForecastTimeline(data.timeline, data.live_intelligence);
  renderActionPlan(data.emergency_action_plan, data.live_intelligence);
  renderOperationalStatus(data);
  currentAssessment = data;
  renderBridgeAnalysis(data.bridge_analysis, data.live_intelligence);
  refreshEmergencyFeed(data);
  renderMap(data.live_intelligence, data.risk);
  workflowStatus.textContent = "Complete";
}

function renderError(message) {
  emptyState.hidden = false;
  results.hidden = true;
  renderLoadingState(false);
  setStatusCard("assessment", "Unavailable", "Assessment did not complete", "degraded");
  emptyState.classList.add("error");
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Assessment unavailable";
  const heading = document.createElement("h2");
  heading.textContent = "Unable to run workflow";
  const detail = document.createElement("p");
  detail.textContent = message;
  emptyState.replaceChildren(eyebrow, heading, detail);
}

function loadDemoScenario() {
  resetOfficialBridgeSelection();
  const values = {
    location: "Albany, NY",
    asset_name: "North River Bridge",
    field_report: "A severe rain band is forecast. Flood debris is accumulating near supports and scour is visible at the foundation.",
    forecast_rainfall_mm: 165,
    forecast_wind_kph: 78,
    river_rise_m: 2.8,
    condition_score: 24,
    asset_age_years: 72,
  };
  Object.entries(values).forEach(([name, value]) => {
    form.elements[name].value = value;
  });
  form.elements.observed_scour.checked = true;
  form.elements.emergency_access_route.checked = false;
  form.elements.use_live_data.checked = false;
  form.elements.demo_scenario.value = "true";
  scenarioStatus.textContent = "Competition scenario loaded: deterministic simulated inputs; live data is disabled for a reliable offline demo.";
}

demoButton.addEventListener("click", loadDemoScenario);
findBridgesButton.addEventListener("click", findOfficialBridges);
officialBridgeSelect.addEventListener("change", selectOfficialBridge);
form.elements.location.addEventListener("input", () => {
  if (form.elements.official_bridge_id.value) {
    resetOfficialBridgeSelection("Location changed. Search and select an official bridge record again.");
    form.elements.asset_name.value = "";
    form.elements.condition_score.value = "";
    form.elements.asset_age_years.value = "";
  }
});
themeToggle.addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
bridgeDetailClose.addEventListener("click", () => {
  if (typeof bridgeDetailDialog.close === "function") bridgeDetailDialog.close();
  else bridgeDetailDialog.removeAttribute("open");
});
document.querySelectorAll("[data-bridge-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.bridgeSort;
    bridgeSort = {
      key,
      direction: bridgeSort.key === key ? bridgeSort.direction * -1 : key === "name" ? 1 : -1,
    };
    renderBridgeTable();
  });
});

try {
  setTheme(localStorage.getItem("aegis-theme") || "dark");
} catch (_) {
  setTheme("dark");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  emptyState.classList.remove("error");
  const fields = new FormData(form);
  const payload = Object.fromEntries(fields.entries());
  ["forecast_rainfall_mm", "forecast_wind_kph", "river_rise_m", "condition_score", "asset_age_years"].forEach((key) => {
    payload[key] = Number(payload[key]);
  });
  payload.observed_scour = fields.get("observed_scour") === "on";
  payload.emergency_access_route = fields.get("emergency_access_route") === "on";
  payload.use_live_data = fields.get("use_live_data") === "on";
  payload.demo_scenario = fields.get("demo_scenario") === "true";
  if (!payload.official_bridge_id) delete payload.official_bridge_id;
  submitButton.disabled = true;
  submitButton.textContent = "Running agents...";
  emptyState.hidden = true;
  results.hidden = true;
  resetWorkflowProgress();
  try {
    renderAssessment(await runStreamedAssessment(payload));
  } catch (error) {
    renderError(error instanceof Error ? error.message : "Unexpected connection failure.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Run risk assessment";
  }
});
