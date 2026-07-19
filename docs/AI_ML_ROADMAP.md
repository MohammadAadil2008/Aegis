# Aegis AI/ML Improvement Roadmap

Aegis should not rush into machine learning. The current deterministic, evidence-cited risk model is the appropriate foundation for an MVP because its inputs, score contributions, limitations, and human-review requirements are visible to operators.

## Phase 1 — Current: explainable deterministic scoring

```text
Evidence → Rules → Risk assessment → Qualified human review
```

The current model combines operator inputs and available public evidence using transparent rules. It produces an elevated-risk screening result, not a probability of bridge collapse, engineering certification, or autonomous operational order.

Strengths to preserve:

- Inspectable score contributions and evidence citations.
- Graceful operation with simulated or partial evidence.
- Clear separation between observations, recommendations, and authority decisions.
- Reproducible assessment and decision snapshots in the audit store when configured.

## Phase 2 — Validated machine learning for elevated-risk screening

Machine learning becomes appropriate only after Aegis has a governed, representative, and validated dataset.

### Candidate training data

```text
Historical bridge incidents and inspection outcomes
             +
Weather conditions and forecasts
             +
Flood and river-gauge levels
             +
Bridge condition, age, geometry, and traffic context
             ↓
   Calibrated elevated-risk screening dataset
```

### Candidate models

- Gradient-boosted trees (for example, XGBoost).
- Random forests.
- Neural networks only when data scale, feature complexity, and validation results justify them.

### Intended output

The model should estimate a **calibrated probability of elevated risk within a defined time horizon**, with confidence bounds and data-quality limits. It must not be described as a collapse-prediction probability unless separately validated for that specific outcome and use case.

### Required safeguards before deployment

1. Define the exact target outcome and prediction horizon with transportation-engineering partners.
2. Use geographically and temporally separated train/validation/test sets to avoid leakage.
3. Compare every candidate model against the deterministic baseline.
4. Measure calibration, precision, recall, false-positive/false-negative rates, and performance across bridge types and regions.
5. Preserve feature attribution, source provenance, model version, and input snapshots for every score.
6. Require qualified human review for all operational decisions.
7. Monitor drift, missing-data behavior, bias, and post-deployment performance; withdraw models that fail defined safety thresholds.

## Phase 3 — Advanced AI and infrastructure intelligence

```text
Satellite imagery + Drone imagery + Sensor streams + Digital-twin simulation
                                   ↓
                  Multimodal infrastructure intelligence
```

After the Phase 2 screening model is validated, Aegis can expand from tabular evidence into multimodal infrastructure intelligence:

- **Satellite imagery:** detect broad flood extent, land movement, and post-event environmental change.
- **Drone imagery:** support qualified inspections with high-resolution visual documentation where safe and authorized.
- **Sensor streams:** ingest governed telemetry such as vibration, displacement, strain, water level, and environmental measurements.
- **Digital twins:** simulate defined engineering scenarios and system impacts using validated asset geometry, material, boundary, and loading assumptions.

Each source must retain timestamp, location, provenance, calibration status, coverage limits, and engineering interpretation. Computer vision and simulation outputs are screening evidence for qualified reviewers; they do not replace inspection, sensor validation, or engineering authority.

## Phase 4 — Decision-support integration

Once a model meets its validation criteria, Aegis can present it alongside—not in place of—the deterministic assessment. Operators should see the time horizon, probability, uncertainty, key contributing features, evidence quality, model version, and a clear human-approval requirement.
