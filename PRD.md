# Final Product Requirements — Opsentia v3
## 1. Identity and customer
**Opsentia — Intelligence That Anticipates.** by **VYRA**, for operational/workforce managers facing scattered dashboards, reactive incident handling, poor decision audit trails and alert fatigue. Entry theme: Future of Work & Enterprise Productivity. One domain-first prototype, reusable analytical architecture; synthetic demonstration data.

**User promise:** Know what changed, understand why, predict what may happen, compare interventions, get accountable human approval, monitor outcomes and learn from actual results.

## 2. End-to-end required journey
1. Replay starts **before** degradation at configurable timestamp (not after breach).
2. COIL computes queue-specific weekday/time baseline, trend, severity and early warning without using future data.
3. Related signals (volume↑, AHT↑, staffing↓, backlog↑) produce **one** fused incident, with state progression WATCH → HIGH → CRITICAL → RECOVERY → RESOLVED, respecting hysteresis and cooldown.
4. Gemini orchestrator fetches operational data, comparable periods, knowledge and historical incidents and produces **supported/contradicted/unknown** hypotheses with citations and tool evidence. If unavailable, screen says `Deterministic fallback; Gemini unavailable`.
5. Decision Lab compares **no action**, +N capacity and donor reallocation with cost, target SLA, protection of donor queue, assumptions, N/A on invalid models.
6. User explicitly reviews one recommendation; approval records identity, role, time, status and rationale. Action pack generates a **simulation-only** staffing notification/task and monitoring checkpoints.
7. Time advances; actual **synthetic observed** KPI is compared with projected result; do not infer causation from unassigned synthetic outcomes. Log prediction error and decision memory.
8. Notifications obey severity-to-recipient matrix, one incident thread and per-channel delivery/ACK ledger; suppressed duplicates remain auditable.

## 3. Seven approved desktop screens and acceptance
| View | Functional minimum | Must not fake |
|---|---|---|
| Live Intelligence | Critical-first alerts, relevant KPIs, expected vs actual, time-to-threshold, recommended actions, active incidents | Future outcomes framed as observed |
| All Metrics | User-selectable queue/date/period, charts, weighted KPIs, cross-queue comparisons | One-day-only filtering or static numbers |
| Investigation | Real Gemini invocation & tool trace, data evidence, hypotheses, past comparable incidents, cited SOPs | AI labels for deterministic text |
| Decision Lab | What-if controls, validated/no-action model, costs, donor risk, constraints and sensitivity | Identical or invented SLA uplift |
| Actions & Approvals | Pending/active/completed, owner, due time, permission gate, append-only audit, outcome status | Approve = real execution without integration |
| Notifications | Per-incident matrix, prepared/attempted/sent/failed/suppressed/ack counts, cooldown and escalation audit | Fake 'sent' messages |
| Historical Analytics | Intraday, weekly, monthly, long-term trend, prior period baselines, heatmap, backtest and incident matches | Future leakage/uncalibrated probability |

Visual design: desktop-first (1366/1440/1920), original VYRA violet-blue-cyan palette, Opsentia brand logo; approved seven reference designs are inspiration not numerical evidence. Maintain seven functional screens with left navigation, no changes to earlier single-page directive unless explicit user approval—**latest agreed scope is seven screens**.

## 4. Priority and release scope
**P0 / blocking**: accurate KPI math + fixture reconciliation; runtime data filters; COIL early warning and incident states; real Gemini tool trace; decision simulation with visible limitations and guardrails; explicit demo approval and ledger; honest notification counts; working Cloud Run URL; tests/video/deck.
**P1 if time**: persistent Firestore for shared reviews, second domain/story, chat follow-ups, downloadable investigation PDF, fully editable notification policy UI.
**Out of scope**: sending real external notifications, editing a corporate workforce platform, advanced trained ML, production authentication/SSO, autonomous real staffing action, fancy animation over functional accuracy.

## 5. Success metrics (measure, do not invent)
- Detection lead-time relative to first *observed* threshold breach, and number of intervals before breach.
- Precision/recall of incident detection on labeled fixtures; duplicate alert suppression and notifications per incident.
- Forecast MAE in SLA percentage points, false-warning rate, coverage and backtest windows.
- Simulated intervention direction, feasibility, donor-queue protection; pre-registered model limitations.
- Human investigation workflow time and tool-call evidence (manual reference versus automated replay, methodology logged).
- Zero high-priority numerical inconsistencies and no wrong simulated/real provenance claims.

## 6. Judging story
40% technical: working Gemini/ADK tools, tests, reliable backend, Cloud Run; 25% impact: time saved and safe decisions measured; 25% innovation: cross-horizon COIL + fused predictive incident + global trade-offs + outcome ledger; 10% design: seven polished workflows. No promised guaranteed score.
