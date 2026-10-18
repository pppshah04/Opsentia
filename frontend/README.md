# Opsentia Frontend Application

This directory contains the client-side user interface for Opsentia, served directly by FastAPI from \rontend/app/\.

## Structure
- \pp/index.html\: Single-page architecture orchestrating the 7 operational screens
- \pp/assets/styles.css\: VYRA theme, sleek dark mode, and responsive layout styling
- \pp/assets/app.js\: REST API client and dynamic client-side state handling
- \pp/assets/opsentia.svg\, \yra.png\: Application branding assets

## Screens
1. **Live Intelligence** — Real-time queue telemetry and anticipatory warnings
2. **All Metrics** — Historical baseline and current operational metric cards
3. **Investigation** — Deep-dive causal analysis with Gemini tool citations
4. **Decision Lab** — Erlang-C capacity simulation with donor queue guardrails
5. **Actions & Approvals** — Audited human approval ledger and action dispatch
6. **Notifications** — Escalation history and alert deduplication matrix
7. **Historical Analytics** — 180-day trend lines and performance distribution
