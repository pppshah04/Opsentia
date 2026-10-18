# Data Contracts and Derivation Rules
`data/synthetic_operations.csv` (43,680 rows, 5 queues, 30-minute intervals) is the authoritative synthetic operating history. `opsentia_all_queues_30min.csv`, daily/weekly/monthly files are precomputed aggregates to **recompute and reconcile**. Other 20 files are policy, knowledge, incident, notification and decision *fixtures*.

## Critical numerical rules
- Each row uniquely keyed by `(timestamp, queue)`; timezone explicit in UI; no duplicate keys.
- `answered_calls`, `abandoned_calls`, `sla_met_calls` nonnegative integer, `sla_met_calls <= answered_calls`, `0 <= SLA <= 1` (verify representation), AHT seconds >=0.
- Queue flow: **backlog_opening + offered_calls = answered_calls + abandoned_calls + backlog_closing** (or documented events such as spill/transfer). Do not assume offered=answered+abandoned when backlog changes.
- Weighted service level: `sum(sla_met_calls) / sum(answered_calls)` if denominator is answered; verify contract before display. Never simple-average SLA% across intervals.
- Weighted AHT: `sum(total_handling_seconds) / sum(answered_calls)` if matching definitions.
- Abandon rate: abandoned / offered (check policy), not reconstructed from SLA.
- Occupancy: handling / available capacity for same interval; use actual per-row units, warn when >1.
- Staffing capacity in agent-minutes: available agents * 30 minutes; workload = answered * AHT seconds / 60; chart staff requirement from documented queueing model not random multiplier.
- Forecast accuracy from both forecast and actual volumes and documented convention; percentage errors undefined when denominator zero.
- Future data leakage forbidden: for forecast at t, no features from t+30 and no outcome used to select model/threshold for t.
- Decision simulation outputs cannot be read from `opsentia_decision_scenario_inputs.csv`: that file has **inputs** and `predictions_status`, not validated uplift predictions.
- `opsentia_notification_events.csv` and action ledger are **simulated**, not proof that recipients got an email or real staffing occurred.
- Historical similarity matches: heuristic method and denominators; not calibrated probability.

## Data coverage
`synthetic_operations.csv`: 43,680 rows = 182 days * 48 intervals * 5 queues. 26 CSV total. Data fixtures not licensed real records.

## Data lineage UI rule
Every chart/metric displays `as_of`, time range, queue(s), source, observed vs forecast/simulated. Changing filters refreshes charts and narrative together. Historical reference uses prior comparison periods only.
