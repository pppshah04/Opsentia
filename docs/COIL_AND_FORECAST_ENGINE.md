# COIL: Continuous Operations Intelligence Layer
## Purpose
Continuous incident state across new 30-minute observations; meaningful early warnings, history-aware baselines and multi-horizon recommendations without spamming notifications or claiming calibrated risk from heuristic scores.

## Services
`ingest_validate` → `baseline` → `anomaly/trend` → `pattern_fusion` → `risk_and_forecast` → `incident_state_manager` → `notifications` → `investigation` → `outcome_monitor`.
For demo mode use **replay scheduler** advancing through synthetic observations at controlled increments, ideally 1 interval/step. Real-time worker optional; no actual production streaming claim.

## Baselines by metric
- Absolute policy floor/ceiling where appropriate, and empirical distribution of comparable past periods.
- Intraday 4/8 previous intervals; medium 4 comparable weeks; longer 8–12 weeks and 3–6 months where sufficient.
- Time of day, day of week and explicitly known events; suppress expected planned spikes only if risk is still low.
- Report deviation in *percentage points* for percentages when appropriate vs *relative percent* for rates/time/counts. Label which.
- Missing data/insufficient sample => UNKNOWN / watch, never authoritative prediction.

## Trend, early warning and severity
- At t compute observed deviation, count of consecutive adverse intervals, magnitude, slope/velocity, cross-KPI pressure, estimated business footprint, historical matching and quality flag.
- Forecast t+30/60/90 with a baseline model using only prior observations; add prediction intervals based on rolling error if backtested; do not claim P(breach)>X without calibrated evaluation.
- Risk dimensions shown individually; transparent configurable weights are illustrative until cross-validated. Map NORMAL, WATCH, HIGH, CRITICAL with policy thresholds and severe objective breaches.
- **Breach** defined independently of slope: already below SLA floor => breach, even if recovering; forecasted crossing while presently above floor => early warning.
- Severity hysteresis: 2 consecutive normal intervals before downgrade, cooldown on same incident/recipient, immediate critical upgrade when true floor breach; recovery and resolution are separate states.

## Incident fusion
One incident key `(queue, overlapping-time-window, common-operational-pattern)` with all signal IDs attached; track incident_id and first/last seen, suspected causes not asserted as fact. Never create a new incident for each metric. Maintain owner, state, severity, time-to-breach estimate, observed breach if any, and dedup key.

## Forecast validation
Create walk-forward windows and compare last-known baseline, linear trend, and COIL forecast; track MAE in SLA points, timing error and precision/recall of first breach warnings, Brier/calibration only if probabilities implemented, missed alert rate, duplicate thread rate. Compute on 5 queues/6 months with train cutoffs, not random shuffle. Include difficult tests: spikes/false positives/planned events, 0 volume, no history, missing records, staggered signals, flapping.

## Trigger orchestration
On new/high incident create investigation job; cap Gemini calls with state transition triggers and explicit user clicks (cost control). Every interval recomputes severity/recovery deterministically. Use rate limits, retries and idempotent keys.
