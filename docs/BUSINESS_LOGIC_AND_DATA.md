# Business logic, data model and mathematical correctness
## Source hierarchy
**Authority:** `data/synthetic_operations.csv`, `(queue,timestamp)` unique, 43,680 observations (182 days × 48 intervals × 5 queues). Derived: all-queues-30min, daily, weekly, monthly, model backtests, metric baselines. Metadata/event fixtures: incidents, rules, policies, knowledge catalog, scenario inputs, action/notification/outcome histories. No files may be silently edited to match design mockups.

## Definitive formulas and denominator discipline
For aggregate window W and queue set Q:
- Offered = Σoffered_calls; Answered = Σanswered_calls; Abandoned = Σabandoned_calls; Met = Σsla_met_calls.
- **SLA** = Met / Answered *100 when Answered>0; target SLA read from policy/source. Do not average subperiod SLAs.
- **Abandonment** = Abandoned / Offered *100 when Offered>0. Calls moved to backlog make offered≠answered+abandoned for a single interval.
- **Queue conservation**: opening backlog + offered = answered + abandoned + closing backlog (if the fixture defines no extra transfers). Document any additional transfers; validate rows and sums.
- **AHT** = Σtotal_handling_seconds / Σanswered_calls; confirm same time unit and selected window. For zero answered return null.
- **Occupancy** = Σhandling_seconds / Σavailable_agent_minutes ×60, clipped for display only if source is mathematically capped; preserve invalid raw values as validation errors. If `available_agents` already net of absence, do not subtract shrinkage twice.
- **Capacity**: available-agent-minutes = available_agents×30; workload-agent-minutes = total_handling_seconds/60. Staffing gap = required_agents - available_agents; required_agents model must be explicit and not taken as physical truth without a definition.
- **Forecast accuracy** choose exactly one documented metric: `1 - Σ|forecast-offered|/Σoffered` (WAPE complement), floor at 0; do not confuse with mean of per-interval accuracies. Show `N/A` when Σoffered=0.
- **Productivity** = Σanswered_calls / Σavailable_agent_hours (only where denominator reflects actual logged activity); interval UPH is not case UPH.
- **Backlog** closing stock for final timestamp in selected window; *never* sum backlog across intervals for a headline.
- **Response time/ASA** use weighted counts if valid; never display raw average without measured per-call denominators.

## Data integrity validations
1. Correct schema and types, timestamp order, null policy, uniqueness and 30-minute cadence per queue.
2. Answered/abandoned/met integers nonnegative; `sla_met <= answered`; all proportion 0..1; backlog nonnegative.
3. Queue flow invariants across intervals and groups, with no unaccounted creation/disappearance.
4. Daily/weekly/monthly derived series recompute from interval source to tolerance; mismatch blocks release.
5. Replay `as_of` filters **all** historical series, policy versions, documents and events to known-at-time data. Visual future actual data hidden unless replay has progressed.
6. Action and notification fixtures labeled `SIMULATED` even if status says SENT/COMPLETED.
7. Any policy threshold must cite the policy row used (not a hidden 90% rule).

## Historical navigation and expected baseline
- 30-min observations, comparable same weekday and time-of-day, prior 4/8 weeks; minimum N and fallback for sparse partitions.
- rolling intraday 4/8 intervals; weekly 7/28 day comparisons; monthly calendar/rolling; long-term trend across 182 days (not a full annual seasonality claim).
- seasonality in data only covers ~6 months; cannot infer yearly seasonal effects reliably.
- Baseline median, trimmed mean or percentile bands; metric direction configurable (AHT high bad, SLA low bad).
- Expose baseline data count and interval/percentile band with observed value.

## Incidents and knowledge
`opsentia_incidents` and similar histories are synthetic labels. Similarity methods must specify features (volume, AHT, staffing, SLA trajectory, planned event), normalization, temporal horizon, ranking, sample count and whether known at the time; similarity score is not empirical probability.

## Worked example — historical replay
At t=16:30, query data for *t and before*. Show current Queue A SLA and compare with historical matched slots. Forecast t+30 using only previous values. At 17:00, reveal actual breach if it occurred, compute lead time `breach_at - warning_at`, forecast error `|predicted - observed|` in percentage points, and update incident from WATCH/HIGH to CRITICAL. Avoid calling that time 59 minutes if observations support 30 minutes.
