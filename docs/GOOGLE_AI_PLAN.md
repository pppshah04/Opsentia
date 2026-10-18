# Google AI — Mandatory Meaningful Implementation
**Judging focus:** technical merit, meaningful GenAI. A badge that says 'AI Generated' is not enough.

## Shortest credible architecture
One **Google ADK Gemini investigation agent** (or google-genai function-calling agent if ADK integration blocks the deadline) + deterministic read-only tools behind Pydantic models. Deploy with FastAPI to Cloud Run, using official Google Cloud ADK documentation. Model selection must be current and verified at runtime, never hardcoded as an inaccurate brand claim.

## Minimal tools (all return machine-readable evidence/source)
1. `get_snapshot(queue, as_of)` — observed metrics, prior interval, source.
2. `get_baseline(queue, metric, as_of, comparable_weeks)` — as-of historical distribution.
3. `get_trend_and_forecast(queue, as_of, horizon_minutes)` — measured trend, uncertainty and backtest limitations.
4. `get_related_incidents(queue, as_of)` — matches and outcomes but no future incidents.
5. `search_knowledge(query, as_of)` — cited document_id, effective version, conflicts.
6. `evaluate_scenarios(incident_id, scenarios)` — deterministic constraints/donor impact only.
7. `get_alert_history(incident_id)` — severity, count, notifications and decision status.

## Agent flow
A) UI calls `/api/investigate` for a specific `incident_id`, `as_of`. B) Agent must fetch snapshot and historical baselines then choose additional tools. C) Compare at least 2 hypotheses with support/contradiction/unknowns. D) If insufficient evidence, abstain. E) Propose feasible interventions with cited simulation outputs. F) Return structured response: `summary`, `investigation_steps`, `hypotheses`, `evidence_ids`, `known_unknowns`, `forecast`, `recommended_action`, `approval_required`, `model_id`, `tool_trace_id`, `execution_mode`.

## Execution safety
Model cannot approve or send anything; backend exposes read-only tools to AI. Human approval changes state server-side; notifications only via channel adapters with delivery acknowledgments. Redact user prompts. Prompt injection tests for knowledge docs. Fallback must be displayed as deterministic, not Gemini.

## Evidence needed
- Screen recording showing `Investigate with Google AI`.
- Server trace JSON of actual Gemini response/model and tool calls (at least 3 distinct real tools).
- One positive incident and one 'insufficient evidence' response.
- `.env` not committed. Provide public Google Cloud URL and deployment logs.

## Source documentation
https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk
https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-adk-service
