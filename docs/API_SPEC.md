# API specification and integration contracts
The existing `GET /`, `/api/health`, `/api/data-coverage`, `/api/snapshot`, `/api/ui/bootstrap` routes are **existing** and should remain backward compatible. `bootstrap` currently returns `meta,current,summary,baseline,rolling,queue_comparison,timeline,active_incidents,selected_incident,evidence,matches,scenarios,forecast,notification_summary,notifications,actions,action_log,daily,weekly,monthly,queue_catalog,escalation_matrix,knowledge,hourly_heatmap`.

## Proposed new / enhanced routes (not currently implemented)
| Method/path | Purpose | Permission | Test |
|---|---|---|---|
| GET `/api/coil/snapshot?queue=&as_of=` | risk, baseline, trend, forecast, state; prior-only | read | time travel/no leakage |
| POST `/api/coil/replay/advance` | deterministic interval step for demo | demo only | 16:30→17:00 visible |
| GET `/api/incident/{id}` | active signals, state, timeline, owner, counts | read | single incident thread |
| POST `/api/incident/{id}/acknowledge` | append acknowledgment | demo approver | idempotent |
| POST `/api/investigate` | **real** Gemini/ADK invocation | server model credential | trace tools + fallback |
| GET `/api/ai/status` | live verified vs fallback/status | read | false before success |
| GET `/api/investigations/{id}/trace` | sanitized model/tool trace | scoped read | no secrets |
| POST `/api/simulations` | calculate options, guardrails | read/authorized demo | predictable constrained math |
| GET `/api/incident/{id}/scenarios` | prior scenario runs | read | provenance |
| POST `/api/decisions` | draft decision with explicit scenario | demo approver | no auto approval |
| POST `/api/decisions/{id}/approve` | approved synthetic action | authorized demo | transition audit |
| POST `/api/decisions/{id}/reject` | rejection and rationale | authorized demo | durable |
| GET `/api/actions?incident_id=` | owner, due, state, audit | read | accurate overdue |
| GET `/api/notifications?incident_id=` | event ledger and counts | read | counts reconcile |
| GET `/api/analytics?queue=&from=&to=&grain=` | intraday/weekly/monthly/long-term | read | weighted results |
| GET `/api/policies` | effective incident/escalation policies | read | as-of versions |
| GET `/api/demo/metrics` | demo performance/test truth | read | source evidence |

## Required envelope on factual responses
```json
{"data":{},"meta":{"as_of":"...","timezone":"fixture timezone not specified","queue":"Queue A","window":"30m","origin":"SYNTHETIC_OBSERVED|DERIVED|FORECAST|SIMULATION_INPUT|SIMULATION_OUTPUT|GEMINI_LIVE|DETERMINISTIC_FALLBACK","model_version":"...","verified":false},"warnings":[]}
```
Existing API may preserve its shape; new endpoints MUST include equivalent fields without disrupting UI.

## API errors
400 invalid input/policy, 401/403 restricted mutation, 404 no known incident, 409 invalid transition/idempotency collision, 422 schema error, 429 rate limit, 503 model/service unavailable with deterministic fallback if safe. Unit-consistent numeric data, JSON null rather than NaN.

## UI contract
Selectors update every relevant chart/API request; `data-origin` provenance appears in tooltip/header; model status never hardcoded; state update returns updated counts and history; recent actions and notifications filtered to selected incident when in incident context; all HTML rendered safely.
