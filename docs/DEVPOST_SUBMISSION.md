# Aegis Devpost submission handoff

## Project summary

Aegis is an infrastructure-intelligence and emergency decision-support application for qualified human reviewers. Operators can select an official U.S. bridge record, combine field observations with public weather, flood, routing, and infrastructure evidence, and receive a source-cited, deterministic risk assessment, agent trace, recommended review priorities, and PDF incident report.

It is decision support only. Aegis does not certify structural condition, predict bridge failure, issue closures or evacuation orders, or replace qualified engineering and emergency-management authority.

## How Codex and GPT-5.6 were used

Codex, using GPT-5.6, was the development collaborator for the core product work: the Dockerized FastAPI architecture, public-data adapters, asynchronous multi-agent workflow, official bridge lookup, deterministic and explainable risk assessment, dashboard, PDF reporting, safety boundaries, testing, documentation, and submission hardening.

The deployed runtime does not claim to use GPT-5.6. It uses Groq only as an optional writing and evidence-synthesis integration. The deterministic Aegis risk level remains independent of that integration, and the app falls back to source-cited deterministic content if Groq is unavailable or produces invalid output.

Codex `/feedback` Session ID: `019f7556-2ac8-7ce3-b26c-eb8a6dcc3210`.

## Submission links and assets

- Repository: https://github.com/MohammadAadil2008/Aegis
- Live demo: https://aegis-0fuy.onrender.com/
- Screenshot set: [docs/screenshots](screenshots/README.md)
- Demo script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- Video: add the public YouTube URL after upload.

## Verification performed

- Local automated tests: 28 passed, including PDF-report tests.
- Live-city verification: Albany, NY resolved public FHWA NBI record `351511` (RTE 9W); a valid three-page PDF report was returned.
- The screenshot set contains no secrets or personal data.

## Suggested Devpost description

When storms, flooding, and infrastructure concerns converge, teams need a fast, transparent way to organize what is known without pretending to replace an engineer. Aegis turns operator observations and public infrastructure, weather, flood, and routing evidence into an explainable screening assessment. Its asynchronous specialist agents collect and label evidence, while deterministic scoring keeps the displayed risk level inspectable. The workflow produces source-cited actions for qualified human review and a shareable PDF incident report.

For a repeatable demo, load the built-in flood-threat scenario. For real locations, search and select an official FHWA National Bridge Inventory record. Aegis clearly labels public-data limits and never represents its assessment as a certified engineering prediction, closure order, evacuation order, or dispatch directive.
