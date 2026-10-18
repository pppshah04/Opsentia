"""Opsentia — Full-Day Performance Forecast & Backtest Service (v3.4)
Replaces naive trend extrapolation with a mathematically grounded End-Of-Day (EOD) operational forecast.
Calculates observed-to-date counts plus prior-only historical expected remaining intervals.
Handles capacity-constrained backlog accumulation and stress-day autoregressive shock decay.
Team VYRA · Google Cloud AI Builder Cup 2026.
"""
from __future__ import annotations
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import timedelta
import pandas as pd


class OpsentiaForecastService:
    """Full-Day EOD forecasting engine using strictly prior-only baselines and capacity stock-flows."""

    def __init__(self, ops_df: pd.DataFrame, inc_df: Optional[pd.DataFrame] = None):
        self.raw_df = ops_df.copy().sort_values('timestamp').reset_index(drop=True)
        self.raw_df['date'] = self.raw_df['timestamp'].str.slice(0, 10)
        self.raw_df['time'] = self.raw_df['timestamp'].str.slice(11, 19)

        if inc_df is not None:
            self.inc_df = inc_df.copy()
        else:
            candidate_paths = [
                Path('data/opsentia_incidents.csv'),
                Path(__file__).parent.parent / 'data' / 'opsentia_incidents.csv',
            ]
            loaded = False
            for p in candidate_paths:
                if p.exists():
                    try:
                        self.inc_df = pd.read_csv(p)
                        loaded = True
                        break
                    except Exception:
                        pass
            if not loaded:
                self.inc_df = pd.DataFrame()

    def get_full_day_forecast(
        self,
        queue: str = 'Queue A',
        as_of: str = '2026-09-13 16:30:00',
        target_sla: float = 0.90,
    ) -> Dict[str, Any]:
        """Compute end-of-day operational forecast for the selected queue and date."""
        day = as_of[:10]
        as_of_time = as_of[11:19]
        as_of_dt = pd.Timestamp(as_of)

        # ------------------------------------------------------------------
        # ALL QUEUES AGGREGATION: Aggregate individual queue forecasts
        # Ensures exactly 48 time buckets per day and exact count conservation
        # ------------------------------------------------------------------
        if queue == 'All Queues':
            individual_queues = sorted([q for q in self.raw_df['queue'].unique() if q != 'All Queues'])
            q_forecasts = {q: self.get_full_day_forecast(queue=q, as_of=as_of, target_sla=target_sla) for q in individual_queues}

            if all(fc.get('status') == 'NO_DATA' for fc in q_forecasts.values()):
                return {
                    'queue': 'All Queues',
                    'as_of': as_of,
                    'day': day,
                    'status': 'NO_DATA',
                    'message': f'No observed intervals for All Queues on {day} up to {as_of}.',
                }

            valid_fcs = [fc for fc in q_forecasts.values() if fc.get('status') != 'NO_DATA']
            first_fc = valid_fcs[0]
            num_intervals = len(first_fc['all_intervals'])

            all_intervals = []
            for i in range(num_intervals):
                t_stamp = first_fc['all_intervals'][i]['timestamp']
                t_time = first_fc['all_intervals'][i]['time']
                kind = first_fc['all_intervals'][i]['kind']

                int_offered = sum(fc['all_intervals'][i]['offered_calls'] for fc in valid_fcs)
                int_answered = sum(fc['all_intervals'][i]['answered_calls'] for fc in valid_fcs)
                int_abandoned = sum(fc['all_intervals'][i]['abandoned_calls'] for fc in valid_fcs)
                int_sla_met = sum(fc['all_intervals'][i]['sla_met_calls'] for fc in valid_fcs)
                int_agents = sum(fc['all_intervals'][i]['available_agents'] for fc in valid_fcs)
                int_backlog = sum(fc['all_intervals'][i]['backlog'] for fc in valid_fcs)
                int_handle_sec = sum((fc['all_intervals'][i].get('aht_seconds') or 0.0) * fc['all_intervals'][i]['answered_calls'] for fc in valid_fcs)

                int_sla = (int_sla_met / int_answered) if int_answered > 0 else None
                int_aht = round(int_handle_sec / int_answered, 1) if int_answered > 0 else 0.0

                all_intervals.append({
                    'timestamp': t_stamp,
                    'time': t_time,
                    'kind': kind,
                    'offered_calls': int_offered,
                    'answered_calls': int_answered,
                    'abandoned_calls': int_abandoned,
                    'sla_met_calls': int_sla_met,
                    'sla': round(int_sla, 4) if int_sla is not None else None,
                    'sla_pct': round(int_sla * 100, 1) if int_sla is not None else None,
                    'aht_seconds': int_aht,
                    'available_agents': int_agents,
                    'backlog': int_backlog,
                })

            observed_intervals = [item for item in all_intervals if item['kind'] == 'OBSERVED']
            future_intervals = [item for item in all_intervals if item['kind'] == 'PROJECTED']

            act_offered = sum(item['offered_calls'] for item in observed_intervals)
            act_answered = sum(item['answered_calls'] for item in observed_intervals)
            act_abandoned = sum(item['abandoned_calls'] for item in observed_intervals)
            act_sla_met = sum(item['sla_met_calls'] for item in observed_intervals)
            act_sec = sum((item.get('aht_seconds') or 0.0) * item['answered_calls'] for item in observed_intervals)
            act_sla = (act_sla_met / act_answered) if act_answered > 0 else None
            act_backlog = observed_intervals[-1]['backlog'] if observed_intervals else 0

            fut_offered = sum(item['offered_calls'] for item in future_intervals)
            fut_answered = sum(item['answered_calls'] for item in future_intervals)
            fut_abandoned = sum(item['abandoned_calls'] for item in future_intervals)
            fut_sla_met = sum(item['sla_met_calls'] for item in future_intervals)
            fut_sec = sum((item.get('aht_seconds') or 0.0) * item['answered_calls'] for item in future_intervals)
            fut_sla = (fut_sla_met / fut_answered) if fut_answered > 0 else None

            total_offered = act_offered + fut_offered
            total_answered = act_answered + fut_answered
            total_abandoned = act_abandoned + fut_abandoned
            total_sla_met = act_sla_met + fut_sla_met
            total_sec = act_sec + fut_sec

            eod_sla = (total_sla_met / total_answered) if total_answered > 0 else None
            eod_sla_pct = round(eod_sla * 100, 2) if eod_sla is not None else None
            eod_abandon = (total_abandoned / total_offered) if total_offered > 0 else None
            eod_aht = round(total_sec / total_answered, 1) if total_answered > 0 else None
            eod_backlog = all_intervals[-1]['backlog'] if all_intervals else 0

            any_high_uncertainty = any(fc.get('projected_full_day', {}).get('risk_level') == 'HIGH_UNCERTAINTY' for fc in valid_fcs)
            risk_level = 'HIGH_UNCERTAINTY' if any_high_uncertainty else 'NORMAL_OPERATIONS'
            margin = 3.0 if any_high_uncertainty else 1.2
            sla_lower_pct = round(max(0.0, (eod_sla_pct or 90.0) - margin), 2)
            sla_upper_pct = round(min(100.0, (eod_sla_pct or 90.0) + (margin * 0.8)), 2)

            return {
                'queue': 'All Queues',
                'as_of': as_of,
                'day': day,
                'forecast_type': first_fc['forecast_type'],
                'model_name': 'COIL_EOD_FORECAST_V1',
                'is_day_complete': first_fc['is_day_complete'],
                'target_sla': target_sla,
                'target_sla_pct': round(target_sla * 100, 1),
                'actual_to_date': {
                    'intervals_count': len(observed_intervals),
                    'offered_calls': act_offered,
                    'answered_calls': act_answered,
                    'abandoned_calls': act_abandoned,
                    'sla_met_calls': act_sla_met,
                    'sla': round(act_sla, 4) if act_sla is not None else None,
                    'sla_pct': round(act_sla * 100, 2) if act_sla is not None else None,
                    'aht_seconds': round(act_sec / act_answered, 1) if act_answered > 0 else None,
                    'current_backlog': act_backlog,
                },
                'predicted_remaining': {
                    'intervals_count': len(future_intervals),
                    'offered_calls': fut_offered,
                    'answered_calls': fut_answered,
                    'abandoned_calls': fut_abandoned,
                    'sla_met_calls': fut_sla_met,
                    'sla': round(fut_sla, 4) if fut_sla is not None else None,
                    'sla_pct': round(fut_sla * 100, 2) if fut_sla is not None else None,
                },
                'projected_full_day': {
                    'sla': round(eod_sla, 4) if eod_sla is not None else None,
                    'sla_pct': eod_sla_pct,
                    'target_breached': bool(eod_sla is not None and eod_sla < target_sla),
                    'offered_calls': total_offered,
                    'answered_calls': total_answered,
                    'abandoned_calls': total_abandoned,
                    'abandon_rate': round(eod_abandon, 4) if eod_abandon is not None else None,
                    'abandon_rate_pct': round(eod_abandon * 100, 2) if eod_abandon is not None else None,
                    'aht_seconds': eod_aht,
                    'end_backlog': eod_backlog,
                    'risk_level': risk_level,
                    'sla_lower_pct': sla_lower_pct,
                    'sla_upper_pct': sla_upper_pct,
                    'range_type': 'HEURISTIC_SCENARIO_RANGE',
                    'sla_range_type': 'HEURISTIC_SCENARIO_RANGE',
                    'range_label': 'Heuristic Scenario Range (Uncalibrated)',
                },
                'all_intervals': all_intervals,
                'total_day_intervals': len(all_intervals),
                'observed_intervals_count': len(observed_intervals),
                'projected_intervals_count': len(future_intervals),
                'queue_breakdowns': {q: fc.get('projected_full_day') for q, fc in q_forecasts.items()},
                'assumptions': first_fc.get('assumptions', []),
                'limitations': first_fc.get('limitations', []),
            }

        # ------------------------------------------------------------------
        # SINGLE QUEUE FORECAST
        # ------------------------------------------------------------------
        q_df = self.raw_df[self.raw_df['queue'] == queue]
        obs_df = q_df[(q_df['date'] == day) & (q_df['timestamp'] <= as_of)]

        if obs_df.empty:
            return {
                'queue': queue,
                'as_of': as_of,
                'day': day,
                'status': 'NO_DATA',
                'message': f'No observed intervals for queue {queue} on {day} up to {as_of}.',
            }

        # Observed totals
        obs_offered = int(obs_df['offered_calls'].sum())
        obs_answered = int(obs_df['answered_calls'].sum())
        obs_abandoned = int(obs_df['abandoned_calls'].sum())
        obs_sla_met = int(obs_df['sla_met_calls'].sum())
        obs_sla = (obs_sla_met / obs_answered) if obs_answered > 0 else None
        obs_handle_sec = float((obs_df['answered_calls'] * obs_df['aht']).sum()) if 'aht' in obs_df.columns else 0.0
        obs_end_backlog = int(obs_df['backlog'].iloc[-1]) if 'backlog' in obs_df.columns else 0

        # Check if day is complete (as_of >= 23:30)
        is_day_complete = bool(as_of_time >= '23:30:00')

        # Operating day 48 intervals (00:00 to 23:30)
        all_times = [f'{h:02d}:{m:02d}:00' for h in range(24) for m in (0, 30)]
        remaining_times = [t for t in all_times if t > as_of_time]

        # Prior 4 weeks seasonal baseline
        prior_dates = [(as_of_dt - timedelta(days=w * 7)).strftime('%Y-%m-%d') for w in range(1, 5)]
        hist_pool = q_df[q_df['date'].isin(prior_dates)]

        # Check for active incident as of as_of (strictly prior: start_at <= as_of)
        has_active_inc = False
        inc_type = None
        if not self.inc_df.empty and 'start_at' in self.inc_df.columns:
            active_inc = self.inc_df[
                (self.inc_df['queue'] == queue) &
                (self.inc_df['start_at'] <= as_of) &
                (self.inc_df['start_at'].str.startswith(day))
            ]
            if not active_inc.empty:
                has_active_inc = True
                inc_type = active_inc['incident_type'].iloc[0] if 'incident_type' in active_inc.columns else None

        # Telemetry disruption check
        latest_obs = obs_df.iloc[-1]
        latest_sla = (latest_obs['sla_met_calls'] / latest_obs['answered_calls']) if latest_obs['answered_calls'] > 0 else 0.85

        recent_obs = obs_df.tail(4)
        recent_hist = hist_pool[hist_pool['time'].isin(recent_obs['time'].unique())]
        if not recent_hist.empty and recent_hist['offered_calls'].mean() > 0:
            vol_ratio = max(0.5, min(1.8, recent_obs['offered_calls'].mean() / recent_hist['offered_calls'].mean()))
            base_recent_sla = float(recent_hist['sla_met_calls'].sum() / recent_hist['answered_calls'].sum()) if recent_hist['answered_calls'].sum() > 0 else 0.90
        else:
            vol_ratio = 1.0
            base_recent_sla = 0.90

        sla_deficit = max(0.0, base_recent_sla - latest_sla)
        is_disrupted = bool(has_active_inc or (latest_sla < 0.85 and sla_deficit > 0.08) or (obs_end_backlog > 20))
        risk_level = 'HIGH_UNCERTAINTY' if is_disrupted else 'NORMAL_OPERATIONS'

        future_intervals = []
        fut_offered_total = 0
        fut_answered_total = 0
        fut_abandoned_total = 0
        fut_sla_met_total = 0
        fut_handle_sec_total = 0.0

        current_running_backlog = obs_end_backlog

        if not is_day_complete and remaining_times:
            for k, t_str in enumerate(remaining_times, start=1):
                t_hist = hist_pool[hist_pool['time'] == t_str]
                if has_active_inc and k <= 7:
                    surge_mult = 1.35 if inc_type in ['CAPACITY_PRESSURE', 'UNEXPECTED_VOLUME', 'MARKETING_SPIKE'] else 1.15
                    effective_vol_ratio = max(vol_ratio, surge_mult) * (0.95 ** (k - 1))
                    effective_vol_ratio = max(1.05, effective_vol_ratio)
                    aht_mult = 1.08
                elif is_disrupted and k <= 4:
                    effective_vol_ratio = max(vol_ratio, 1.20) * (0.90 ** (k - 1))
                    aht_mult = 1.05
                else:
                    effective_vol_ratio = 1.0 + (vol_ratio - 1.0) * (0.80 ** k)
                    aht_mult = 1.00

                if not t_hist.empty:
                    base_offered = float(t_hist['offered_calls'].mean()) * effective_vol_ratio
                    base_aht = (float(t_hist['aht'].mean()) if 'aht' in t_hist.columns else 280.0) * aht_mult
                    base_agents = float(t_hist['available_agents'].mean()) if 'available_agents' in t_hist.columns else 45.0
                    base_sla = float(t_hist['sla_met_calls'].sum() / t_hist['answered_calls'].sum()) if t_hist['answered_calls'].sum() > 0 else 0.85
                    base_abandon = float(t_hist['abandoned_calls'].sum() / t_hist['offered_calls'].sum()) if t_hist['offered_calls'].sum() > 0 else 0.05
                else:
                    base_offered = 80.0 * effective_vol_ratio
                    base_aht = 280.0 * aht_mult
                    base_agents = 40.0
                    base_sla = 0.85
                    base_abandon = 0.05

                if is_disrupted and k <= 6:
                    base_abandon = max(base_abandon, 0.08)

                pred_offered = int(round(base_offered))
                capacity = int(base_agents * (1800.0 / max(30.0, base_aht)) * 0.92)
                total_demand = current_running_backlog + pred_offered
                pred_abandoned = min(total_demand, int(round(pred_offered * base_abandon)))
                pred_answered = min(total_demand - pred_abandoned, capacity)
                current_running_backlog = total_demand - pred_answered - pred_abandoned

                if has_active_inc and k <= 7:
                    deficit_k = max(sla_deficit * (0.92 ** k), 0.35 * (0.92 ** k))
                elif is_disrupted:
                    deficit_k = sla_deficit * (0.85 ** k)
                else:
                    deficit_k = sla_deficit * (0.80 ** k)

                backlog_penalty = min(0.35, (current_running_backlog / max(20, capacity)) * 0.30)
                interval_sla = max(0.30, min(0.99, base_sla - deficit_k - backlog_penalty))
                pred_sla_met = min(pred_answered, int(round(pred_answered * interval_sla)))

                fut_offered_total += pred_offered
                fut_answered_total += pred_answered
                fut_abandoned_total += pred_abandoned
                fut_sla_met_total += pred_sla_met
                fut_handle_sec_total += (pred_answered * base_aht)

                future_intervals.append({
                    'timestamp': f'{day} {t_str}',
                    'time': t_str[:5],
                    'kind': 'PROJECTED',
                    'offered_calls': pred_offered,
                    'answered_calls': pred_answered,
                    'abandoned_calls': pred_abandoned,
                    'sla_met_calls': pred_sla_met,
                    'sla': round(pred_sla_met / pred_answered, 4) if pred_answered > 0 else None,
                    'sla_pct': round((pred_sla_met / pred_answered) * 100, 1) if pred_answered > 0 else None,
                    'aht_seconds': round(base_aht, 1),
                    'available_agents': int(round(base_agents)),
                    'backlog': current_running_backlog,
                })

        # Synthesize complete full-day result
        total_offered = obs_offered + fut_offered_total
        total_answered = obs_answered + fut_answered_total
        total_abandoned = obs_abandoned + fut_abandoned_total
        total_sla_met = obs_sla_met + fut_sla_met_total
        total_handle_sec = obs_handle_sec + fut_handle_sec_total

        eod_sla = (total_sla_met / total_answered) if total_answered > 0 else None
        eod_sla_pct = round(eod_sla * 100, 2) if eod_sla is not None else None
        eod_abandon_rate = (total_abandoned / total_offered) if total_offered > 0 else None
        eod_aht = (total_handle_sec / total_answered) if total_answered > 0 else None
        eod_backlog = current_running_backlog if not is_day_complete else obs_end_backlog

        margin = 3.8 if is_disrupted else 1.2
        sla_lower_pct = round(max(0.0, (eod_sla_pct or 90.0) - margin), 2)
        sla_upper_pct = round(min(100.0, (eod_sla_pct or 90.0) + (margin * 0.7)), 2)

        # Build observed interval items
        observed_intervals = []
        for r in obs_df.itertuples():
            sla_val = (r.sla_met_calls / r.answered_calls) if r.answered_calls > 0 else None
            observed_intervals.append({
                'timestamp': r.timestamp,
                'time': r.timestamp[11:16],
                'kind': 'OBSERVED',
                'offered_calls': int(r.offered_calls),
                'answered_calls': int(r.answered_calls),
                'abandoned_calls': int(r.abandoned_calls),
                'sla_met_calls': int(r.sla_met_calls),
                'sla': round(sla_val, 4) if sla_val is not None else None,
                'sla_pct': round(sla_val * 100, 1) if sla_val is not None else None,
                'aht_seconds': round(float(r.aht), 1) if hasattr(r, 'aht') else None,
                'available_agents': int(r.available_agents),
                'backlog': int(r.backlog),
            })

        forecast_type = 'ACTUAL_FULL_DAY' if is_day_complete else 'EOD_PROJECTED'
        eod_breached = bool(eod_sla is not None and eod_sla < target_sla)

        assumptions = [
            'Prior-only 4-week same-weekday seasonal demand baseline',
            'Residual volume adjustment factor based on trailing 4 observed intervals',
            'Service capacity modeled under available agent roster and handle time',
            'Sequential backlog stock-flow conservation (opening + offered - answered - abandoned = closing)',
            'Autoregressive disruption decay and backlog SLA penalty during active incidents',
        ]
        limitations = [
            'EOD projection is an operational estimate based on historical same-day baselines and capacity models',
            'Uncertainty intervals (sla_lower_pct to sla_upper_pct) are heuristic scenario sensitivity bounds (HEURISTIC_SCENARIO_RANGE), not mathematically calibrated statistical confidence intervals',
            'Demonstrated out-of-range outcomes (e.g. 2026-09-12 16:30 actual 97.96% vs 93.73%-95.77% heuristic band) confirm these ranges reflect stress scenarios rather than calibrated confidence coverage',
            'Does not claim guaranteed breach prevention; serves as early warning decision support',
        ]

        return {
            'queue': queue,
            'as_of': as_of,
            'day': day,
            'forecast_type': forecast_type,
            'model_name': 'COIL_EOD_FORECAST_V1',
            'is_day_complete': is_day_complete,
            'target_sla': target_sla,
            'target_sla_pct': round(target_sla * 100, 1),
            'actual_to_date': {
                'intervals_count': len(obs_df),
                'offered_calls': obs_offered,
                'answered_calls': obs_answered,
                'abandoned_calls': obs_abandoned,
                'sla_met_calls': obs_sla_met,
                'sla': round(obs_sla, 4) if obs_sla is not None else None,
                'sla_pct': round(obs_sla * 100, 2) if obs_sla is not None else None,
                'aht_seconds': round(obs_handle_sec / obs_answered, 1) if obs_answered > 0 else None,
                'current_backlog': obs_end_backlog,
            },
            'predicted_remaining': {
                'intervals_count': len(future_intervals),
                'offered_calls': fut_offered_total,
                'answered_calls': fut_answered_total,
                'abandoned_calls': fut_abandoned_total,
                'sla_met_calls': fut_sla_met_total,
                'sla': round(fut_sla_met_total / fut_answered_total, 4) if fut_answered_total > 0 else None,
                'sla_pct': round((fut_sla_met_total / fut_answered_total) * 100, 2) if fut_answered_total > 0 else None,
            },
            'projected_full_day': {
                'sla': round(eod_sla, 4) if eod_sla is not None else None,
                'sla_pct': eod_sla_pct,
                'target_breached': eod_breached,
                'offered_calls': total_offered,
                'answered_calls': total_answered,
                'abandoned_calls': total_abandoned,
                'abandon_rate': round(eod_abandon_rate, 4) if eod_abandon_rate is not None else None,
                'abandon_rate_pct': round(eod_abandon_rate * 100, 2) if eod_abandon_rate is not None else None,
                'aht_seconds': round(eod_aht, 1) if eod_aht is not None else None,
                'end_backlog': eod_backlog,
                'risk_level': risk_level,
                'sla_lower_pct': sla_lower_pct,
                'sla_upper_pct': sla_upper_pct,
                'range_type': 'HEURISTIC_SCENARIO_RANGE',
                'sla_range_type': 'HEURISTIC_SCENARIO_RANGE',
                'range_label': 'Heuristic Scenario Range (Uncalibrated)',
            },
            'all_intervals': observed_intervals + future_intervals,
            'total_day_intervals': len(observed_intervals) + len(future_intervals),
            'observed_intervals_count': len(observed_intervals),
            'projected_intervals_count': len(future_intervals),
            'assumptions': assumptions,
            'limitations': limitations,
        }

    def backtest_full_day(
        self,
        queue: str = 'Queue A',
        as_of: str = '2026-09-13 16:30:00',
        eval_days: int = 7,
        target_date: Optional[str] = None,
        cutoff_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate empirical forecast error by walking backward over completed days or evaluating a target date."""
        as_of_dt = pd.Timestamp(as_of)
        q_df = self.raw_df[self.raw_df['queue'] == queue] if queue != 'All Queues' else self.raw_df

        if target_date:
            cutoff_t = cutoff_time or '16:30'
            cutoff_ts = f'{target_date} {cutoff_t}:00' if len(cutoff_t) == 5 else f'{target_date} {cutoff_t}'
            fc = self.get_full_day_forecast(queue=queue, as_of=cutoff_ts)
            act_slice = q_df[q_df['date'] == target_date]
            act_offered = int(act_slice['offered_calls'].sum()) if not act_slice.empty else 0
            act_answered = int(act_slice['answered_calls'].sum()) if not act_slice.empty else 0
            act_sla_met = int(act_slice['sla_met_calls'].sum()) if not act_slice.empty else 0
            act_sla_pct = round((act_sla_met / act_answered) * 100, 2) if act_answered > 0 else 0.0
            pred_sla_pct = fc['projected_full_day']['sla_pct'] or 0.0
            err_pp = round(pred_sla_pct - act_sla_pct, 2)
            abs_err = round(abs(err_pp), 2)

            is_inc_day = False
            if not self.inc_df.empty and 'start_at' in self.inc_df.columns:
                match_inc = self.inc_df[
                    ((self.inc_df['queue'] == queue) | (queue == 'All Queues')) &
                    (self.inc_df['start_at'].str.startswith(target_date))
                ]
                is_inc_day = not match_inc.empty

            pred_lower = fc.get('projected_full_day', {}).get('sla_lower_pct')
            pred_upper = fc.get('projected_full_day', {}).get('sla_upper_pct')
            within_range = bool(pred_lower is not None and pred_upper is not None and pred_lower <= act_sla_pct <= pred_upper)

            return {
                'status': 'OK',
                'queue': queue,
                'target_date': target_date,
                'cutoff_time': cutoff_t,
                'projected_sla_pct': pred_sla_pct,
                'actual_completed_sla_pct': act_sla_pct,
                'sla_error_pp': err_pp,
                'absolute_sla_error_pp': abs_err,
                'risk_level': fc.get('projected_full_day', {}).get('risk_level', 'NORMAL_OPERATIONS'),
                'range_type': 'HEURISTIC_SCENARIO_RANGE',
                'sla_range_type': 'HEURISTIC_SCENARIO_RANGE',
                'sla_lower_pct': pred_lower,
                'sla_upper_pct': pred_upper,
                'within_heuristic_range': within_range,
                'is_incident_day': is_inc_day,
                'model_name': 'COIL_EOD_FORECAST_V1',
            }

        # Test across previous days at 16:30 cutoff
        test_dates = [(as_of_dt - timedelta(days=d)).strftime('%Y-%m-%d') for d in range(1, eval_days + 1)]
        records = []

        for d_str in test_dates:
            day_cutoff = f'{d_str} 16:30:00'
            fc = self.get_full_day_forecast(queue=queue, as_of=day_cutoff)
            if fc.get('status') == 'NO_DATA':
                continue

            pred_sla_pct = fc['projected_full_day']['sla_pct']
            pred_vol = fc['projected_full_day']['offered_calls']
            pred_lower = fc['projected_full_day'].get('sla_lower_pct')
            pred_upper = fc['projected_full_day'].get('sla_upper_pct')

            # Actual full day result (at 23:30)
            act_slice = q_df[q_df['date'] == d_str]
            if act_slice.empty:
                continue
            act_offered = int(act_slice['offered_calls'].sum())
            act_answered = int(act_slice['answered_calls'].sum())
            act_sla_met = int(act_slice['sla_met_calls'].sum())
            act_sla_pct = round((act_sla_met / act_answered) * 100, 2) if act_answered > 0 else None

            is_inc_day = False
            if not self.inc_df.empty and 'start_at' in self.inc_df.columns:
                match_inc = self.inc_df[
                    ((self.inc_df['queue'] == queue) | (queue == 'All Queues')) &
                    (self.inc_df['start_at'].str.startswith(d_str))
                ]
                is_inc_day = not match_inc.empty

            if pred_sla_pct is not None and act_sla_pct is not None:
                err_pp = round(pred_sla_pct - act_sla_pct, 2)
                vol_err_pct = round(abs(pred_vol - act_offered) / act_offered * 100, 2) if act_offered > 0 else 0.0
                within_range = bool(pred_lower is not None and pred_upper is not None and pred_lower <= act_sla_pct <= pred_upper)
                records.append({
                    'date': d_str,
                    'cutoff_time': '16:30',
                    'predicted_eod_sla_pct': pred_sla_pct,
                    'actual_eod_sla_pct': act_sla_pct,
                    'sla_error_pp': err_pp,
                    'predicted_lower_pct': pred_lower,
                    'predicted_upper_pct': pred_upper,
                    'within_heuristic_range': within_range,
                    'predicted_volume': pred_vol,
                    'actual_volume': act_offered,
                    'volume_error_pct': vol_err_pct,
                    'is_incident_day': is_inc_day,
                })

        if records:
            mae_sla_pp = round(sum(abs(r['sla_error_pp']) for r in records) / len(records), 2)
            wape_vol_pct = round(sum(abs(r['predicted_volume'] - r['actual_volume']) for r in records) / sum(r['actual_volume'] for r in records) * 100, 2)

            normal_records = [r for r in records if not r['is_incident_day']]
            incident_records = [r for r in records if r['is_incident_day']]
            normal_mae = round(sum(abs(r['sla_error_pp']) for r in normal_records) / len(normal_records), 2) if normal_records else None
            incident_mae = round(sum(abs(r['sla_error_pp']) for r in incident_records) / len(incident_records), 2) if incident_records else None

            coverage_pct = round(sum(1 for r in records if r['within_heuristic_range']) / len(records) * 100, 1)
            normal_cov = round(sum(1 for r in normal_records if r['within_heuristic_range']) / len(normal_records) * 100, 1) if normal_records else None
            inc_cov = round(sum(1 for r in incident_records if r['within_heuristic_range']) / len(incident_records) * 100, 1) if incident_records else None
        else:
            mae_sla_pp = 0.0
            wape_vol_pct = 0.0
            normal_mae = None
            incident_mae = None
            coverage_pct = 0.0
            normal_cov = None
            inc_cov = None

        return {
            'status': 'OK',
            'queue': queue,
            'evaluation_window_days': len(records),
            'cutoff_evaluated': '16:30:00',
            'mean_absolute_error_sla_pp': mae_sla_pp,
            'absolute_sla_error_pp': mae_sla_pp,
            'normal_days_mae_pp': normal_mae,
            'incident_days_mae_pp': incident_mae,
            'normal_days_sample_size': len(normal_records) if records else 0,
            'incident_days_sample_size': len(incident_records) if records else 0,
            'heuristic_range_coverage_pct': coverage_pct,
            'normal_days_range_coverage_pct': normal_cov,
            'incident_days_range_coverage_pct': inc_cov,
            'range_type': 'HEURISTIC_SCENARIO_RANGE',
            'calibration_status': 'UNCALIBRATED_HEURISTIC_BOUNDS',
            'weighted_absolute_percentage_error_volume': wape_vol_pct,
            'model_name': 'COIL_EOD_FORECAST_V1',
            'backtest_records': records,
            'quality_assessment': (
                f'Mean absolute EOD SLA error is {mae_sla_pp} pp across {len(records)} test days '
                f'(Normal days: {normal_mae} pp [n={len(normal_records) if records else 0}], Incident days: {incident_mae} pp [n={len(incident_records) if records else 0}]). '
                f'Heuristic scenario bounds empirical coverage: {coverage_pct}% (Uncalibrated heuristic sensitivity range).'
            ),
        }
