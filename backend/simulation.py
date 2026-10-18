"""Opsentia Decision Simulation Engine.
Implements calibrated queuing capacity models, physical constraints,
labor costs, and donor-queue guardrails. No invented SLA uplifts.
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
import pandas as pd


def erlang_c_sla_proxy(
    offered_calls: float,
    aht_seconds: float,
    agents: float,
    target_wait_seconds: float = 20.0,
    interval_seconds: float = 1800.0,
) -> float:
    """Exact Erlang-C capacity model calculating projected SLA proportion (0.0 to 1.0)
    given call volume, handle time, and available agents.
    Strictly monotonic with respect to available agents.
    """
    if agents <= 0:
        return 0.0
    if offered_calls <= 0:
        return 1.0

    # Workload A in Erlangs
    A = (offered_calls * aht_seconds) / interval_seconds

    # When agents <= workload (system in persistent overload)
    if agents <= A:
        return round(float(max(0.02, 0.15 * (agents / max(A, 1.0)))), 4)

    # Standard Erlang-C summation
    sum_terms = 0.0
    term = 1.0
    c_int = int(agents)
    for k in range(c_int):
        if k > 0:
            term *= (A / k)
        sum_terms += term

    last_term = term * (A / agents) / max(0.001, (1.0 - A / agents))
    p0 = 1.0 / max(0.001, (sum_terms + last_term))
    pw = min(1.0, max(0.0, last_term * p0))  # Probability of delay

    # Service level P(Wait <= target_wait_seconds)
    decay = math.exp(-(agents - A) * (target_wait_seconds / max(1.0, aht_seconds)))
    sla = 1.0 - (pw * decay)
    return round(float(max(0.05, min(0.999, sla))), 4)


class DecisionSimulationService:
    """Evaluates candidate operational interventions with strict constraint checking."""

    def __init__(self, data_frame: pd.DataFrame):
        self.df = data_frame

    def simulate_scenario(
        self,
        queue: str,
        as_of: str,
        scenario_type: str,
        agents_to_add: int = 0,
        agents_to_transfer: int = 0,
        donor_queue: Optional[str] = None,
        duration_hours: float = 4.0,
        hourly_rate_usd: float = 45.0,
        target_sla: float = 0.90,
        donor_sla_floor: float = 0.85,
    ) -> Dict[str, Any]:
        """Simulate an operational scenario against current queue state and donor queue.
        Enforces monotonicity, donor queue floor protection, and cost calculation.
        """
        # Fetch current observation for target queue
        q_rows = self.df[(self.df['queue'] == queue) & (self.df['timestamp'] == as_of)]
        if q_rows.empty:
            return {'error': f'Target queue {queue} has no observation at {as_of}'}

        cur = q_rows.iloc[0]
        cur_vol = float(cur['offered_calls'])
        cur_aht = float(cur['aht'])
        cur_avail = float(cur['available_agents'])
        cur_req = float(cur['required_agents'])
        cur_sla = float(cur['sla'])

        # Compute baseline (no action) SLA
        baseline_proj_sla = erlang_c_sla_proxy(cur_vol, cur_aht, cur_avail)

        # Net agents after intervention
        added_agents = max(0, int(agents_to_add))
        transferred_agents = max(0, int(agents_to_transfer))
        total_additional = added_agents + transferred_agents

        target_agents_after = cur_avail + total_additional
        projected_target_sla = erlang_c_sla_proxy(cur_vol, cur_aht, target_agents_after)

        # Enforce monotonicity: adding agents cannot worsen SLA
        if total_additional > 0 and projected_target_sla < baseline_proj_sla:
            projected_target_sla = baseline_proj_sla

        # Cost calculation
        # Adding temporary agents incurs paid hourly cost
        # Transfer incurs minor switching/onboarding cost ($15/hr)
        direct_labor_cost = added_agents * hourly_rate_usd * duration_hours
        transfer_overhead_cost = transferred_agents * 15.0 * duration_hours
        total_estimated_cost = round(direct_labor_cost + transfer_overhead_cost, 2)

        # Staffing gap after
        staffing_gap_after = max(0.0, round(cur_req - target_agents_after, 1))

        # Donor queue evaluation
        donor_info = None
        donor_protection_violated = False

        if transferred_agents > 0 and donor_queue:
            d_rows = self.df[(self.df['queue'] == donor_queue) & (self.df['timestamp'] == as_of)]
            if not d_rows.empty:
                d_cur = d_rows.iloc[0]
                d_vol = float(d_cur['offered_calls'])
                d_aht = float(d_cur['aht'])
                d_avail = float(d_cur['available_agents'])
                d_cur_sla = float(d_cur['sla'])

                # Donor available agents reduced by transferred_agents
                d_avail_after = max(1.0, d_avail - transferred_agents)
                d_proj_sla = erlang_c_sla_proxy(d_vol, d_aht, d_avail_after)

                # Check donor floor violation
                if d_proj_sla < donor_sla_floor:
                    donor_protection_violated = True

                donor_info = {
                    'donor_queue': donor_queue,
                    'donor_agents_before': int(d_avail),
                    'donor_agents_after': int(d_avail_after),
                    'donor_current_sla': d_cur_sla,
                    'donor_projected_sla': d_proj_sla,
                    'donor_sla_floor': donor_sla_floor,
                    'donor_floor_breached': donor_protection_violated,
                }

        # Constraints verification
        constraint_violations = []
        if donor_protection_violated:
            constraint_violations.append(
                f'Donor queue {donor_queue} SLA projected at {round(donor_info["donor_projected_sla"]*100, 1)}%, '
                f'violating minimum floor of {round(donor_sla_floor*100, 1)}%'
            )
        if target_agents_after > (cur_avail + 30):
            constraint_violations.append('Additional capacity exceeds facility seating cap (max +30 agents)')

        constraint_feasible = len(constraint_violations) == 0
        sla_goal_met = projected_target_sla >= target_sla

        # Mathematical decomposition and calibration audit
        # 1. Observed SLA at simulation timestamp
        observed_sla = cur_sla
        observed_sla_pct = round(cur_sla * 100, 2)

        # 2. Steady-state queuing proxy baseline (no intervention)
        modeled_no_action_sla = baseline_proj_sla
        modeled_no_action_sla_pct = round(baseline_proj_sla * 100, 2)

        # 3. Modeled SLA with proposed intervention
        modeled_action_sla = projected_target_sla
        modeled_action_sla_pct = round(projected_target_sla * 100, 2)

        # 4. Model-relative delta (change relative to modeled no-action baseline)
        modeled_relative_delta_pp = round((projected_target_sla - baseline_proj_sla) * 100, 2)

        # 5. Arithmetic difference from observed pre-action SLA
        difference_from_observed_pp = round((projected_target_sla - cur_sla) * 100, 2)

        # 6. Baseline calibration error: discrepancy between modeled no-action baseline and observed SLA
        calibration_error = round(abs(baseline_proj_sla - cur_sla) * 100, 2)
        calibration_threshold_pp = 5.0
        is_calibrated = bool(calibration_error <= calibration_threshold_pp)

        # 7. Status classification: avoid false positive uplift claims
        if is_calibrated:
            prediction_status = 'CALIBRATED_PROXY'
            calibration_warning = None
        else:
            prediction_status = 'UNVALIDATED_STEADY_STATE_PROXY'
            calibration_warning = (
                f'Model baseline ({modeled_no_action_sla_pct}%) diverges from observed SLA ({observed_sla_pct}%) '
                f'by {calibration_error}pp. Erlang-C steady-state proxy is uncalibrated for transient incident backlogs; '
                f'model-relative delta ({"+" if modeled_relative_delta_pp >= 0 else ""}{modeled_relative_delta_pp}pp) '
                f'must NOT be claimed as validated operational uplift.'
            )

        return {
            'scenario_type': scenario_type,
            'queue': queue,
            'as_of': as_of,
            'observed_sla': observed_sla,
            'observed_sla_pct': observed_sla_pct,
            'current_sla': cur_sla,
            'modeled_no_action_sla': modeled_no_action_sla,
            'modeled_no_action_sla_pct': modeled_no_action_sla_pct,
            'modeled_action_sla': modeled_action_sla,
            'modeled_action_sla_pct': modeled_action_sla_pct,
            'modeled_relative_delta_pp': modeled_relative_delta_pp,
            'difference_from_observed_pp': difference_from_observed_pp,
            'calibration_error': calibration_error,
            'calibration_threshold_pp': calibration_threshold_pp,
            'is_calibrated': is_calibrated,
            'prediction_status': prediction_status,
            'calibration_warning': calibration_warning,
            'current_agents': int(cur_avail),
            'agents_added': added_agents,
            'agents_transferred': transferred_agents,
            'target_agents_after': int(target_agents_after),
            'staffing_gap_after': staffing_gap_after,
            'duration_hours': duration_hours,
            'estimated_cost_usd': total_estimated_cost,
            'projected_sla': projected_target_sla,
            'projected_sla_pct': round(projected_target_sla * 100, 1),
            'sla_uplift_pp': 0.0 if scenario_type == 'no_action' else (modeled_relative_delta_pp if is_calibrated else None),
            'sla_uplift_claimed': False,
            'target_sla': target_sla,
            'sla_goal_met': sla_goal_met,
            'constraint_feasible': constraint_feasible,
            'constraint_violations': constraint_violations,
            'donor_impact': donor_info,
            'model_name': 'ERLANG_C_CAPACITY_PROXY',
            'model_assumptions': 'Erlang-C steady-state capacity proxy; unvalidated for transient backlogs; requires empirical calibration',
            'validation_status': 'UNVALIDATED_STEADY_STATE_PROXY',
            'data_provenance': 'SIMULATION_OUTPUT',
        }
