# Decision Lab — constraints-first, credible counterfactuals
## What currently exists
`opsentia_decision_scenario_inputs.csv` contains **candidate inputs, NOT output uplift**: additional agents, transferred agents, donor queue, durations, cost bases. Do not read missing `projected_sla` as 0 or 100 and do not synthesize a 26-point improvement without a validated model.

## Minimal feasible approach
1. Calculate baseline actual workload and net supply at selected interval and forecast demand for next 30–90 min.
2. Implement a documented **queueing/capacity proxy** with explicit assumptions (arrival rates, AHT service distribution, service-level target interval, abandonment model, warm-start backlog). Prefer Erlang-C only when assumptions fit; otherwise call it a `calibrated_queueing_proxy` or `heuristic` correctly.
3. Calibrate/backtest against synthetic intervals; report MAE and interval/range, sensitivity to AHT, arrival, staffing; use time-separated validation.
4. Run no-action, add N temporary agents, transfer N from donor, routing change only if modelled; any unsupported action returns `UNMODELLED`.
5. Run effects on **target and donor queues** and overall operation, with meaningful labor cost/temporary staffing access constraints; compare smallest feasible option meeting objective.
6. Separate `constraint_feasible` from `sla_goal_met`; no-action can meet policy yet miss performance goal.
7. Return projected SLA and period for *each* option only if model passes validation. If model cannot be validated before deadline, return capacity gap estimates, trade-offs and explicit `SLA projection unavailable` (still credible).

## Invariants and anti-fake tests
- Finite 0..100 SLA; no NaN/Infinity; zero-volume case handled.
- For fixed demand/AHT, increasing *available* agents cannot worsen target queue expected service in basic model; saturation may cause same value but document meaningful plateau. No identical 96% for all capacity changes by hidden cap.
- Decrease donor staffing => donor queue projected service must be recomputed or scenario is blocked/unverified.
- Nonnegative agents, bounded to policy max; labor cost monotonic with added paid labor; transfer not mislabeled completely costless if switching/training costs matter.
- No forecast made from future observed SLA. Outcome after approval must come from later replay data, not force-matched predictions.
- `get_simulation` includes inputs, model version, snapshot, horizon, assumptions, uncertainty, donor effects, constraint list, output type and validation status.

## Human decision flow
Draft scenario → user reviews explicit assumptions → server checks role/policy → decision approved in `SIMULATED_EXECUTION` mode → action event written → later replay → compare projected to synthetic observed with caveat observational outcome does NOT prove action caused improvement.
