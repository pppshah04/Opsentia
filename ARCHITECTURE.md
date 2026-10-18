# Target Technical Architecture — end-to-end
```text
Browser: seven approved desktop screens (existing frontend/app)
    | fetch /api/*; no browser API keys
FastAPI gateway (existing backend/app.py)
    |-- fixture loader + read-only analytics (existing)
    |-- business_metrics.py (to build): counts, denominators, invariants
    |-- coil/ (to build): prior-only baselines, trend, forecast, fusion, risk, state machine
    |-- simulation/ (to build): staffing what-if + donor queue/cost guardrails
    |-- agent/ (to build): Gemini/Google ADK orchestrator + read-only tools + trace
    |-- incidents/ (to build): lifecycle, notification ledger, approval/action audit
    `-- persistence/ (to build): file-based demo locally; Firestore in Cloud Run
Data layer: 26 immutable synthetic CSV fixtures (current), Firestore for mutable events
Deployment: single Cloud Run container with static frontend, FastAPI, protected Gemini key/service identity
```

## Contract boundaries
- Analytics / COIL own all numbers. Gemini selects tools, tests explanations, reads approved SOP content, synthesizes grounded narratives, but does not execute arbitrary SQL/code or approve actions.
- Agent can **read** incident, metrics, evidence, baseline, forecast, relevant policy and scenario models; **never** directly write stakeholder escalation or execute actual staffing.
- Mutable state managed by append-only event ledger in Firestore; local dev in ephemeral SQLite or JSON with clearly documented lifecycle. Cloud Run local file changes are *not* reliable persistence.
- Historical **synthetic dataset** source is `data/synthetic_operations.csv`. 25 other files derived or synthetic fixtures; route through validated service layer.
- Proposed API contracts are in `docs/API_SPEC.md`; don't break existing `/api/ui/bootstrap` or `/api/health` responses.
- Dynamic Gemini model configurable via environment, not hardcoded UI naming; use supported model documented at implementation time.

## Technology stack
Python/FastAPI; pandas/Pydantic/pytest; Google Gen AI SDK or Google ADK; Cloud Run; Google Cloud Secret Manager (recommended); Firestore for durable approval/notifications and model traces if within schedule; BigQuery optional, **not mandatory** for a 43k-row prototype.

## Environment and provenance
`DATA_DIR`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI`, `GEMINI_MODEL`, `GEMINI_API_KEY` (local secure only if required), `APP_MODE=synthetic_replay`, `STATE_BACKEND`, `DEMO_AUTH_MODE`.
Every significant response: `as_of`, `queue`, `period`, `data_origin`, `observed_or_forecast`, `model_version`, `generated_at`, `verification_state`.

## Sequence
COIL detects signal → stores incident ID → Gemini `get_*` tools → typed investigation → simulation alternatives → recommendation constraints → user decision → server approval state → notification event(s) → replay observations → outcome ledger → historical lookup next time.
