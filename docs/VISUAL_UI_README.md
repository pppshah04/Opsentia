# Opsentia visual application — developer guide

**Product** Opsentia — Intelligence That Anticipates.  
**Team** VYRA

This is an actual code implementation of the seven approved desktop UI concepts. It uses the **26 synthetic CSV fixtures** with a small FastAPI backend and **framework-free HTML/CSS/JavaScript**. No npm, Node, image-generation service, or CDN is needed to run it.

## Run on your PC

Requirements: Python 3.11+; install from this repository's `requirements.txt`.

```bash
python -m pip install -r requirements.txt
python scripts/preflight_data.py
python -m pytest -q
python -m uvicorn backend.app:app --reload --port 8080
```

Open **http://localhost:8080/** in a desktop browser. All seven screens share the same sidebar. Select a queue, replay date, and 30-minute interval in the top header. Choose the standard demo date `2026-09-13` and time `17:00` for the Queue A incident; choose any date in the fixture range to inspect other intervals.

## Screens implemented

1. Live Intelligence — current critical warning, observed vs uncalibrated trend, relevant evidence, historical matches, decision inputs, notification history.
2. All Metrics — KPI tiles, eight interactive chart contexts, cross-queue comparison.
3. Investigation — incident timeline, evidence, competing hypotheses, organizational knowledge references.
4. Decision Lab — candidate input comparison, staffing gap calculation, constraints; **no unvalidated SLA uplift claims**.
5. Actions & Approvals — recorded fixture action ledger, review state and outcome caveats.
6. Notifications — event counts, suppressed records, delivery-fixture ledger and escalation policies.
7. Historical Analytics — weekly, monthly, daily charts, true 28-day queue-hour weighted SLA heatmap and past matches.

## Accuracy and status

- **SYNTHETIC REPLAY**, not a live business integration; all operational records are synthetic.
- No live Google Gemini call has been verified. The UI correctly labels it as **AI unverified** and provides no fake agent trace.
- `opsentia_decision_scenario_inputs.csv` contains options and costs, but **no validated counterfactual SLA effects**. The Decision Lab does not invent them.
- Notifications are *simulated event fixtures*, not actual sent messages. Recorded actions are also synthetic.
- Forecast lines use an **uncalibrated naive time-series method**; not validated probabilities or proven no-action futures.
- Dates in the dataset are synthetic operating times. UI labels demo replay rather than implying those timestamps reflect live wall-clock conditions.
- The supplied Opsentia and VYRA marks are reused; a compact transparent VYRA crop improves readability on the dark sidebar.

## Architecture

`backend/app.py` serves the SPA `/` and `/assets/*` plus `/api/ui/bootstrap`, `/api/data-coverage`, `/api/snapshot`, `/api/health`.

The backend uses Pandas to load/aggregate CSV data and FastAPI to serve JSON. Browser charts are SVG rendered by JS, avoiding external chart dependencies. All numerical KPI values and the historical heatmap originate in the data and Python aggregations.

## Production integration still needed

This is the **visual application code**, not a completed production Opsentia release. Future work: calibrated queue/staffing simulation, verified Gemini tool calls with persisted traces, verified approvals/action execution, protected user accounts, durable notification ledger, Cloud Run integration and browser E2E tests against deployed endpoints.

## Build and deployment

The existing `Dockerfile` includes backend/frontend/data. For local container execution:

```bash
docker build -t opsentia-ui .
docker run --rm -p 8080:8080 opsentia-ui
```

If deploying to Cloud Run, avoid claiming that a deployment or real AI call has occurred until independently confirmed.
