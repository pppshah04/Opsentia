# Verification matrix and scoring evidence
## Baseline
As of 2026-10-17 original seven-screen project: **9/9 tests pass**, data preflight **PASS**, Gemini **not verified**, Cloud Run **not verified**, mutable approval/notifications **not built**. These baseline facts are not completion evidence.

## Gates
The machine-readable source is `qa/RELEASE_GATES.csv`; each has owner, status, evidence URL/path and test command. Critical gates must be **PASS**; any `UNVERIFIED` must be disclosed. Do not mark '10/10'.

## Functional and numerical tests
1. 26 CSV presence and registry; 43,680 observed queue intervals; cross-check all aggregate sources.
2. Backlog flow, answered/abandon, weighted SLA/AHT, occupied capacity, WAPE and no divide-by-zero.
3. `as_of` time travel stops every chart, history, tools and policy retrieval from reading future.
4. Alert sign and slope-independent threshold breach; predicted warning before observed breach with measured lead-time.
5. Same incident grouping/dedup, flapping suppression, escalation for new recipients, severity downgrade on sustained recovery.
6. 3+ intervention inputs and outputs; feasible vs objective met, donor-queue floor, monotonic effects or explicit invalid.
7. Read-only real Gemini tool loop with trace and citations; missing data and injection/failed-model fallbacks.
8. Per-incident event counts prepared/attempted/simulated sent/failed/suppressed/ack; never mix real and synthetic.
9. Action states only legal transitions; reject non-owner or unauthenticated mutations; replay-clock due/overdue correctness.
10. Seven screens at 1366/1440/1920; valid filters and interactions, no NaN, escaped content and accessible focus controls.
11. Secret scan, container health, deployed URL, live model trace, performance logging and code repository.
12. Three-minute video from actual deployed app; official-template pitch PDF and link list, not rendered concept art.

## Competitor score mapping (targets, not guarantees)
Technical 40: model/tool execution proof, valid math, tests, deployment, failure handling.
Problem impact 25: measured early warning and time-saving method, stakeholder escalation/action lifecycle.
Innovation 25: fused incident, alternate futures, cross-queue protection, outcome learning.
UX 10: seven polished desktop screens with coherent critical-first flow and clear provenance.

## Reproducible KPI benchmarking
Provide labeled fixture ground-truth incidents; set time-ordered train/validation split, evaluate alert precision, recall, lead-time, duplicates, false positives, SLA MAE in percentage points and method. Compare no-COIL threshold baseline vs COIL. Show N, mean/median and uncertainty; don't cherry-pick single best replay. Report invocation latency on local vs Cloud Run separately and reference date/time. If unable, label numbers 'prototype demonstration only'.
