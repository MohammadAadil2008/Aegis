# Aegis - AI Infrastructure Risk Assessment & Emergency Decision Support Platform

Project status handoff based on the current repository contents.

The project has been renamed to **Aegis** across the application, API title, package name, UI, PDF report, and documentation.

## 1. Project Mission and Problem Statement

Aegis is an AI-powered infrastructure intelligence platform that helps emergency managers identify bridge risks by combining live environmental conditions, infrastructure data, and explainable AI reasoning. The current implementation is an explainable, human-in-the-loop emergency decision-support MVP for bridges, especially during flood conditions. It is designed to help an operator collect public evidence, select a real U.S. bridge record, run a deterministic risk assessment, and generate emergency-management outputs before conditions escalate.

The problem it addresses is fragmented emergency evidence. Weather forecasts, river gauges, bridge inventory data, mapped infrastructure, public alerts, and operator field reports normally live in separate systems. Aegis combines those inputs into a single reviewable dashboard and report.

This is decision-support software only. It does not issue closure orders, evacuation orders, engineering certifications, or true collapse predictions. A qualified engineer, state DOT, emergency manager, or other authorized human must review operational decisions.

## 2. Current Features Implemented

- FastAPI backend serving a static web dashboard at `/`.
- Health endpoint at `/api/health`.
- Official bridge search endpoint at `/api/bridges`.
- Assessment endpoints:
  - `POST /api/assessments`
  - `POST /api/assessments/stream`
- PDF report endpoint:
  - `GET /api/assessments/{assessment_id}/report.pdf`
- Emergency feed endpoint:
  - `GET /api/emergency-feed`
- U.S. city/state/ZIP search with nearby official bridge candidates from the FHWA National Bridge Inventory.
- Server-side re-verification of selected bridge records before scoring.
- Official bridge metadata support:
  - bridge name
  - coordinates
  - route
  - location description
  - year built
  - normalized condition score
  - deck/superstructure/substructure condition codes
  - average daily traffic
  - inspection date when available
  - source and limitations
- Live public evidence collection with short timeouts and independent failure handling.
- Shared live-evidence snapshot reused by specialist agents.
- Asynchronous multi-agent workflow:
  - Weather Agent
  - Flood Agent
  - Infrastructure Agent
  - Routing Agent
  - Emergency Planning Agent
  - Coordinator Agent
- Streaming NDJSON progress updates for agent status.
- Deterministic risk score from `LOW`, `MODERATE`, `HIGH`, or `CRITICAL`.
- Explainability panel with score components, positive evidence, negative evidence, confidence rationale, missing data, and source IDs.
- Optional Groq narrative enhancement for public alert and situation report drafts.
- Optional Groq Incident Commander that creates a source-cited operational brief.
- Guardrails that prevent the Groq Incident Commander from changing the deterministic risk level.
- 24-hour conditions timeline with `Now`, `2 hours`, `6 hours`, `12 hours`, and `24 hours`.
- Emergency action plan with immediate, 30-minute, 2-hour, 12-hour, communication, inspection, and resource-deployment sections.
- Live emergency feed that separates verified agency alerts from Aegis assessments.
- Nearby bridge exposure table with sortable bridge risk, importance, distance, nearby hospitals, nearby schools, traffic impact, and alternative crossings.
- Interactive Leaflet map with bridge markers, flood-screening circle, radar tile support, route geometry, and nearby context.
- PDF incident report generated after completed assessments.
- Dockerized deployment with non-root container user, dropped Linux capabilities, and `no-new-privileges`.
- Basic browser security headers and in-memory rate limiting.
- Unit tests and API tests covering core risk behavior, streaming, PDF generation, emergency feed, bridge lookup parsing, official bridge re-verification, source citation validation, rate limiting, and security headers.

## 3. Features Planned but Not Implemented

The repository lists these as next production milestones or clearly identifies them as future work:

- Full Aegis branding is implemented across the UI, API, reports, and documentation.
- Authenticated NASA FIRMS wildfire and satellite imagery adapters are **not implemented yet**.
- Database-backed source snapshots are **not implemented yet**.
- Durable operator audit trail is **not implemented yet**.
- Postgres/PostGIS storage is **not implemented yet**.
- Role-based access control is **not implemented yet**.
- Operator approval workflow is **not implemented yet**.
- Calibrated scoring with historical validated bridge-incident data is **not implemented yet**.
- Precision/recall evaluation for prediction quality is **not implemented yet**.

Capabilities absent from the current codebase and important to label honestly:

- True ML collapse-prediction model is **not implemented yet**.
- Real-time structural sensor ingestion is **not implemented yet**.
- Verified road-closure detours around a selected bridge are **not implemented yet**.
- Official floodplain, evacuation-zone, or closure-order generation is **not implemented yet**.
- Persistent PDF/report storage is **not implemented yet**.
- User accounts, authentication, and authorization are **not implemented yet**.

## 4. Current Technology Stack

- Backend language: Python 3.11+.
- Backend framework: FastAPI.
- ASGI server: Uvicorn.
- Data validation: Pydantic.
- HTTP client: httpx.
- Environment loading: python-dotenv.
- Optional LLM provider: Groq Python SDK.
- PDF generation: ReportLab.
- PDF test extraction: pypdf.
- Testing: pytest and FastAPI TestClient.
- Frontend: static HTML, CSS, and vanilla JavaScript.
- Mapping: Leaflet from unpkg CDN.
- Containerization: Docker and Docker Compose.
- Runtime package name: `aegis-api`.

## 5. Architecture Overview

The application is a single-service MVP.

```text
Browser dashboard
    |
    | HTTP / NDJSON stream
    v
FastAPI application
    |
    | validates request with Pydantic
    v
IncidentCoordinator
    |
    | optional selected bridge re-verification
    v
BridgeCatalogService - FHWA NBI
    |
    | shared public evidence snapshot
    v
LiveDataService - weather, flood, gauge, alerts, map, route, terrain
    |
    | async specialist execution
    v
Weather/Flood/Infrastructure/Routing agents
    |
    v
Emergency Planning Agent
    |
    v
Coordinator Agent - deterministic score and explanation
    |
    +--> optional Groq narrative/Incident Commander
    +--> 24-hour timeline
    +--> bridge exposure analysis
    +--> emergency action plan
    +--> PDF incident report
```

The safety-critical risk level is deterministic. Groq is used only for optional writing and evidence synthesis. The Groq Incident Commander output is validated so it cannot cite unknown sources or change the deterministic risk level.

The backend is intentionally modular:

- API routing lives in `backend/app/main.py`.
- Request/response contracts live in `backend/app/schemas.py`.
- Public-data adapters live in `backend/app/services/live_data.py` and related service modules.
- Bridge inventory lookup lives in `backend/app/services/bridge_catalog.py`.
- Multi-agent workflow code lives in `backend/app/services/agent_workflow/`.
- Report and planning generators live in separate service modules.

## 6. Folder Structure Explanation

```text
.
|-- README.md
|-- docker-compose.yml
|-- backend/
|   |-- Dockerfile
|   |-- pyproject.toml
|   |-- app/
|   |   |-- main.py
|   |   |-- schemas.py
|   |   |-- config.py
|   |   |-- services/
|   |   |   |-- agent_workflow/
|   |   |   |-- action_plan.py
|   |   |   |-- bridge_analysis.py
|   |   |   |-- bridge_catalog.py
|   |   |   |-- commander.py
|   |   |   |-- emergency_feed.py
|   |   |   |-- forecast_timeline.py
|   |   |   |-- groq.py
|   |   |   |-- live_data.py
|   |   |   |-- orchestrator.py
|   |   |   |-- pdf_report.py
|   |   |   |-- rate_limit.py
|   |   |   `-- report_store.py
|   `-- tests/
|-- frontend/
|   |-- index.html
|   |-- app.js
|   `-- styles.css
`-- docs/
    |-- DEMO_SCRIPT.md
    `-- PROJECT_STATUS.md
```

- `README.md`: primary setup, architecture, security notes, demo instructions, and production milestones.
- `backend/app/main.py`: FastAPI app, routes, middleware, rate limits, PDF serving, and static frontend serving.
- `backend/app/schemas.py`: all typed API contracts and internal structured data models.
- `backend/app/services/orchestrator.py`: coordinates bridge verification, live data, agents, timeline, bridge analysis, action plan, Groq, and final response.
- `backend/app/services/agent_workflow/`: independent agents and Coordinator Agent.
- `backend/app/services/live_data.py`: public API adapters and caching.
- `backend/app/services/bridge_catalog.py`: FHWA bridge lookup and official record parsing.
- `backend/app/services/commander.py`: optional evidence-constrained Groq Incident Commander.
- `backend/app/services/groq.py`: optional Groq narrative drafting.
- `backend/app/services/pdf_report.py`: server-side incident report PDF creation.
- `backend/tests/`: backend unit and API tests.
- `frontend/`: static emergency-operations dashboard.
- `docs/DEMO_SCRIPT.md`: two-minute competition demo script.

## 7. Data Sources Being Used

Implemented data sources:

- FHWA National Bridge Inventory through the hosted ArcGIS feature service.
- Open-Meteo Geocoding API for resolving city/state/ZIP-style locations.
- Open-Meteo Forecast API for precipitation, wind gusts, and weather code.
- Open-Meteo Flood API for GloFAS river-discharge forecasts.
- USGS Water Services legacy NWIS instantaneous-values endpoint for nearby gauge stage/flow.
- National Weather Service active alerts API.
- USGS Earthquake Catalog for recent nearby seismic events.
- RainViewer public weather maps API for radar tile metadata.
- Open-Meteo elevation endpoint for terrain elevation.
- OpenStreetMap through Overpass API for nearby bridges and critical infrastructure.
- OSRM public routing service for an illustrative regional route.
- Optional 511NY road and bridge events when `NY511_API_KEY` is configured.

Data sources named in repository roadmap but **not implemented yet**:

- NASA FIRMS wildfire data.
- Satellite imagery adapters.

Other public APIs may be good future candidates, but they are not documented as implemented integrations in the current repository.

## 8. AI/ML Approach

The current system is not a trained ML collapse-prediction model.

Implemented approach:

- Deterministic rule/score model implemented by the Coordinator Agent.
- Specialist agents convert structured inputs and live evidence into typed JSON-like `AgentFinding` objects.
- Coordinator Agent combines weather/water, infrastructure vulnerability, access risk, and field-report signals into a 0-100 score.
- Risk thresholds:
  - `LOW`: below 35
  - `MODERATE`: 35-59
  - `HIGH`: 60-79
  - `CRITICAL`: 80+
- Confidence is currently a fixed screening confidence of 55%.
- Explainability is source-cited through structured `CitedStatement` and `ScoreComponent` objects.
- Groq can optionally generate writing improvements and an Incident Commander brief, but it does not control the risk score.

Not implemented yet:

- Supervised learning model trained on historical bridge failures.
- Probability of collapse.
- Model calibration against real incident outcomes.
- Precision, recall, ROC/AUC, or other prediction-quality metrics.
- Computer vision analysis of satellite, drone, or inspection images.
- Structural simulation or digital twin modeling.

## 9. APIs and Integrations

Backend APIs implemented:

- `GET /`
  - Serves the static dashboard.
- `GET /api/health`
  - Returns minimal service health.
- `GET /api/bridges?location=...`
  - Searches official FHWA bridge candidates near a resolved location.
- `POST /api/assessments`
  - Runs a full assessment and returns the final JSON response.
- `POST /api/assessments/stream`
  - Runs a full assessment and streams progress plus the final result as NDJSON.
- `GET /api/emergency-feed?latitude=...&longitude=...&location=...`
  - Returns verified public alerts for the current area.
- `GET /api/assessments/{assessment_id}/report.pdf`
  - Downloads an in-memory PDF report for a completed assessment.

Environment integrations:

- `GROQ_API_KEY`
- `GROQ_MODEL`
- `ENABLE_GROQ_ENRICHMENT`
- `ENABLE_GROQ_INCIDENT_COMMANDER`
- `NY511_API_KEY`

## 10. Current Development Progress

The repository is at a strong MVP stage:

- Core backend assessment workflow is implemented.
- Multi-agent orchestration is implemented.
- Real public weather, flood, water, alert, bridge, map, route, radar, elevation, and infrastructure adapters are implemented.
- Official U.S. bridge lookup is implemented.
- Source-cited explainability is implemented.
- Dashboard UI is implemented as a static frontend.
- PDF report export is implemented.
- Docker deployment is implemented.
- Tests exist for important backend behavior.

The project is not yet production-ready for real emergency operations. It is appropriate as a hackathon/portfolio MVP if it is clearly presented as decision support and not as a certified prediction or public-safety authority.

## 11. Bugs, Limitations, and Technical Risks

- Branding mismatch resolved: code and docs now use Aegis consistently.
- The FHWA NBI data is official inventory/inspection data, not live structural sensor data.
- The bridge ID currently uses the feature layer `fid`; a more durable canonical bridge identifier should be introduced.
- NBI condition score normalization is simple and needs transportation-engineering validation.
- The risk scoring weights are hand-built and not calibrated with historical bridge incident data.
- Confidence is fixed at 55% rather than computed from data availability and source quality.
- Live flood discharge is contextual evidence only; it is not converted into risk points because no local stage/discharge threshold is validated.
- USGS water integration uses the legacy NWIS endpoint; migration to the newer USGS water API should be planned.
- OSRM routing is illustrative and does not verify actual bridge closure detours.
- Flood-screening overlay is not an official flood zone or evacuation boundary.
- Manual field report text and manual fallback inputs can still influence risk.
- Public API calls rely on free external services with rate limits, outages, and changing schemas.
- PostgreSQL/PostGIS audit storage persists assessment, evidence, source, risk, bridge-geometry, and operator-decision records when `DATABASE_URL` is configured. PDF storage, rate limiting, and cache state remain in-memory and do not work across multiple app instances.
- PDF reports expire from memory and disappear on restart.
- No user authentication, authorization, or role-based access control exists.
- Report downloads are protected only by unguessable IDs and expiration, which is not enough for public deployment.
- CSP allows Leaflet from unpkg and inline styles; this is acceptable for MVP but should be tightened for production.
- The audit schema exists, but it needs database migrations, retention policies, encrypted backups, monitoring, and authenticated operator identities before production use.
- No frontend end-to-end tests are present.
- No CI pipeline is present in the repository.
- No load testing or provider contract testing is present.
- No secrets manager integration is present.
- The app should not be deployed publicly with real operational data until auth, audit logging, HTTPS, and data governance are added.

## 12. Recommended Next Development Steps

1. Keep the Aegis branding consistent as new features, reports, and screenshots are added.
2. Replace the bridge `fid` identifier with a more durable FHWA/NBI identifier strategy.
3. Add database migrations, retention policies, backups, and monitoring around the implemented Postgres/PostGIS audit store; move PDF reports to authenticated encrypted object storage.
4. Add authentication and role-based authorization.
5. Add an operator approval workflow for alerts, closure recommendations, and PDF reports.
6. Add a durable audit trail that stores exact source payload snapshots used in every assessment.
7. Improve confidence scoring so it reflects source availability, source freshness, bridge-record completeness, and manual-input reliance.
8. Replace illustrative OSRM routing with real origin/destination routing and closure-aware detour logic.
9. Add provider contract tests for FHWA, Open-Meteo, USGS, NWS, Overpass, and OSRM payloads.
10. Add frontend end-to-end tests for bridge selection, streamed assessment, map rendering, PDF export, and emergency feed.
11. Add CI checks for tests, formatting, dependency vulnerability scanning, and secret scanning.
12. Plan USGS API migration away from legacy NWIS endpoints.
13. Build a calibrated research version of the score using historical bridge incidents and document validation metrics.

## 13. Long-Term Product Vision

The current Aegis MVP combines weather data, flood data, bridge inventory records, and AI agents into an explainable risk assessment. Its long-term direction is an **Infrastructure Intelligence Platform** that can incorporate:

- Satellite imagery and remote-sensing change detection.
- IoT bridge-sensor telemetry.
- Validated historical failures and inspection outcomes for model calibration.
- Computer-vision findings from inspections and imagery.
- Digital-twin simulation for engineering scenarios.
- AI agents that synthesize evidence, surface uncertainty, and support qualified human decisions.

This vision is deliberately broader than bridge-collapse prediction. Aegis should help infrastructure operators understand evolving risk, prioritize inspection and response, and coordinate resilient operations. Any future predictive or simulation capability must be validated against engineering standards and remain subject to human authority.

## 14. Improvements Needed to Make This Hackathon and Portfolio Ready

Highest-impact improvements:

- Capture fresh Aegis screenshots after the next UI verification pass.
- Add a polished README with screenshots, architecture diagram, demo GIF, safety disclaimer, setup instructions, and API examples.
- Add a Mermaid architecture diagram showing the multi-agent workflow and data-source pipeline.
- Add a clear roadmap separating hackathon MVP, portfolio version, and production version.
- Add a short demo dataset or scripted scenario that judges can run even if public APIs are slow.
- Add a visible "Real data vs manual fallback" indicator in the dashboard so judges trust what is live.
- Add a source freshness panel showing when each data source was retrieved.
- Add a concise decision-support and model-limitations explanation in the README to show engineering maturity.
- Add CI with pytest and basic static checks.
- Add screenshots or a short video demo to `README.md`.
- Add frontend end-to-end tests for the main demo path.
- Add better route language: "illustrative route" should stay obvious everywhere until routing is verified.
- Add a public-safe deployment checklist before hosting it beyond local Docker.

Suggested follow-on artifacts:

- GitHub README.
- Mermaid architecture diagram.
- Development roadmap.
- Implementation task list.

These can be generated directly from this handoff document.
