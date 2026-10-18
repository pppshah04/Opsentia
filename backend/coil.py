"""Opsentia Continuous Operations Intelligence Layer (COIL).
Provides prior-only baselines (zero future leakage), multi-horizon early warning,
velocity/trend detection, and fused incident lifecycle management with hysteresis.
"""
from __future__ import annotations
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from backend.business_metrics import compute_weighted_kpis, classify_sla_severity


class CoilEngine:
    """Core analytics engine for continuous operational risk monitoring."""

    def __init__(self, data_frame: pd.DataFrame):
        self.df = data_frame

    def get_prior_baseline(
        self,
        queue: str,
        as_of: str,
        lookback_weeks: int = 4
    ) -> Dict[str, Any]:
        """Compute baseline strictly from prior matching weekday/time slots before as_of.
        Guarantees NO future leakage.
        """
        as_of_dt = pd.Timestamp(as_of)
        as_of_weekday = as_of_dt.dayofweek
        slot = as_of[11:]  # 'HH:MM:SS'

        # Filter strictly < as_of, same queue, matching time slot
        prior_mask = (
            (self.df['queue'] == queue) &
            (self.df['timestamp'] < as_of) &
            (self.df['timestamp'].str.endswith(slot))
        )
        prior_df = self.df[prior_mask].copy()

        if prior_df.empty:
            return {
                'sample_count': 0,
                'queue': queue,
                'as_of': as_of,
                'lookback_weeks': lookback_weeks,
                'metrics': compute_weighted_kpis(pd.DataFrame()),
                'note': 'Insufficient historical records prior to as_of.'
            }

        # Filter to exact same weekday
        prior_df['weekday'] = pd.to_datetime(prior_df['timestamp']).dt.dayofweek
        same_day_prior = prior_df[prior_df['weekday'] == as_of_weekday].sort_values('timestamp')
        
        # Take the most recent lookback_weeks samples
        selected = same_day_prior.tail(lookback_weeks)
        kpis = compute_weighted_kpis(selected)

        # Standard deviations for confidence intervals
        std_sla = float(selected['sla'].std()) if len(selected) > 1 else 0.0
        std_vol = float(selected['offered_calls'].std()) if len(selected) > 1 else 0.0
        std_aht = float(selected['aht'].std()) if len(selected) > 1 else 0.0

        return {
            'sample_count': len(selected),
            'queue': queue,
            'as_of': as_of,
            'lookback_weeks': lookback_weeks,
            'sla': kpis['sla'],
            'sla_std': round(std_sla, 4),
            'offered_calls': kpis['offered_calls'] // max(len(selected), 1),
            'offered_calls_std': round(std_vol, 1),
            'aht': kpis['aht'],
            'aht_std': round(std_aht, 1),
            'available_agents': kpis['available_agents'],
            'occupancy': kpis['occupancy'],
            'abandon_rate': kpis['abandon_rate'],
            'metrics': kpis,
            'timestamps_used': selected['timestamp'].tolist(),
        }

    def get_recent_trend(
        self,
        queue: str,
        as_of: str,
        intervals: int = 6
    ) -> Dict[str, Any]:
        """Examine intra-day trend across preceding intervals on the same day up to as_of."""
        as_of_dt = pd.Timestamp(as_of)
        day_str = as_of[:10]

        day_mask = (
            (self.df['queue'] == queue) &
            (self.df['timestamp'].str.startswith(day_str)) &
            (self.df['timestamp'] <= as_of)
        )
        recent = self.df[day_mask].sort_values('timestamp').tail(intervals)

        if recent.empty:
            return {'intervals': 0, 'sla_slope': 0.0, 'consecutive_adverse': 0, 'series': []}

        sla_series = [float(x) for x in recent['sla'].tolist()]
        times = [x[11:16] for x in recent['timestamp'].tolist()]

        # Compute slope in SLA percentage points per interval
        if len(sla_series) >= 2:
            sla_slope = (sla_series[-1] - sla_series[0]) / (len(sla_series) - 1)
        else:
            sla_slope = 0.0

        # Count consecutive intervals below 0.90 target
        consecutive_adverse = 0
        for s in reversed(sla_series):
            if s < 0.90:
                consecutive_adverse += 1
            else:
                break

        # AHT trend
        aht_series = [float(x) for x in recent['aht'].tolist()]
        aht_slope = (aht_series[-1] - aht_series[0]) / (len(aht_series) - 1) if len(aht_series) >= 2 else 0.0

        return {
            'intervals': len(recent),
            'sla_slope_pp': round(sla_slope * 100, 2),
            'sla_slope_raw': round(sla_slope, 4),
            'aht_slope_sec': round(aht_slope, 1),
            'consecutive_adverse': consecutive_adverse,
            'current_sla': sla_series[-1],
            'series': [
                {
                    'time': times[i],
                    'sla': round(sla_series[i] * 100, 1),
                    'aht': round(aht_series[i], 1),
                    'volume': int(recent['offered_calls'].iloc[i]),
                    'agents': int(recent['available_agents'].iloc[i]),
                }
                for i in range(len(times))
            ]
        }

    def compute_early_warning_and_breach(
        self,
        queue: str,
        as_of: str,
        sla_floor: float = 0.75,
        target_sla: float = 0.90
    ) -> Dict[str, Any]:
        """Detect operational degradation and compute lead-time before first observed floor breach.
        If current SLA is already below floor, mark as observed breach.
        If current SLA is above floor but falling, compute time-to-breach.
        """
        current_rows = self.df[(self.df['queue'] == queue) & (self.df['timestamp'] == as_of)]
        if current_rows.empty:
            return {'status': 'UNKNOWN', 'reason': 'No current observation'}

        cur = current_rows.iloc[0]
        cur_sla = float(cur['sla'])
        trend = self.get_recent_trend(queue, as_of, intervals=6)
        baseline = self.get_prior_baseline(queue, as_of, lookback_weeks=4)

        slope = trend['sla_slope_raw']
        base_sla = baseline.get('sla', 0.90)

        # Deviation from baseline in percentage points
        sla_gap_target_pp = round((cur_sla - target_sla) * 100, 1)
        sla_gap_baseline_pp = round((cur_sla - base_sla) * 100, 1)

        is_observed_breach = cur_sla < sla_floor
        predicted_breach = False
        time_to_breach_min = None
        predicted_breach_timestamp = None

        if is_observed_breach:
            state = 'CRITICAL'
            status_desc = f'Observed breach: SLA {round(cur_sla*100, 1)}% is below {round(sla_floor*100, 1)}% floor'
            time_to_breach_min = 0
        elif cur_sla < 0.85:
            state = 'HIGH'
            status_desc = f'High risk: SLA {round(cur_sla*100, 1)}% is below 85% warning threshold'
            if slope < 0:
                intervals_to_floor = (cur_sla - sla_floor) / abs(slope)
                time_to_breach_min = max(30, int(round(intervals_to_floor)) * 30)
                predicted_breach = True
                pred_dt = pd.Timestamp(as_of) + timedelta(minutes=time_to_breach_min)
                predicted_breach_timestamp = pred_dt.strftime('%Y-%m-%d %H:%M:%S')
        elif cur_sla < 0.90 or (slope < -0.02 and cur['required_agents'] > cur['available_agents']):
            state = 'WATCH'
            status_desc = f'Early warning: SLA {round(cur_sla*100, 1)}% under downward pressure'
            if slope < 0:
                intervals_to_floor = (cur_sla - sla_floor) / abs(slope)
                time_to_breach_min = max(30, int(round(intervals_to_floor)) * 30)
                predicted_breach = True
                pred_dt = pd.Timestamp(as_of) + timedelta(minutes=time_to_breach_min)
                predicted_breach_timestamp = pred_dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            state = 'NORMAL'
            status_desc = 'Operating within acceptable thresholds'

        return {
            'queue': queue,
            'as_of': as_of,
            'current_sla': cur_sla,
            'target_sla': target_sla,
            'sla_floor': sla_floor,
            'state': state,
            'status_description': status_desc,
            'is_observed_breach': is_observed_breach,
            'predicted_breach': predicted_breach,
            'time_to_breach_minutes': time_to_breach_min,
            'predicted_breach_timestamp': predicted_breach_timestamp,
            'sla_gap_target_pp': sla_gap_target_pp,
            'sla_gap_baseline_pp': sla_gap_baseline_pp,
            'trend': trend,
            'baseline_sla': base_sla,
            'available_agents': int(cur['available_agents']),
            'required_agents': int(cur['required_agents']),
            'staffing_gap': int(cur['required_agents']) - int(cur['available_agents']),
        }

    def correlate_incident_signals(
        self,
        incident_id: str,
        as_of: str
    ) -> List[Dict[str, Any]]:
        """Extract multi-signal evidence for the given incident and as_of without future data."""
        # Find active incident
        signals = []
        q_mask = (self.df['timestamp'] == as_of)
        for _, row in self.df[q_mask].iterrows():
            q = row['queue']
            base = self.get_prior_baseline(q, as_of)
            cur_sla = float(row['sla'])
            base_sla = base.get('sla', 0.90)
            cur_vol = int(row['offered_calls'])
            base_vol = base.get('offered_calls', cur_vol)
            cur_aht = float(row['aht'])
            base_aht = base.get('aht', cur_aht)

            # SLA signal
            if cur_sla < 0.88:
                signals.append({
                    'signal_id': f'SIG-{q}-SLA-{as_of[11:16]}',
                    'incident_id': incident_id,
                    'metric': 'service_level',
                    'queue': q,
                    'observed_value': round(cur_sla * 100, 1),
                    'comparable_baseline': round(base_sla * 100, 1),
                    'deviation': round((cur_sla - base_sla) * 100, 1),
                    'unit': 'pp',
                    'severity': 'CRITICAL' if cur_sla < 0.75 else 'HIGH' if cur_sla < 0.85 else 'WATCH',
                })

            # Volume signal
            if base_vol > 0 and (cur_vol - base_vol) / base_vol > 0.10:
                rel_pct = round(((cur_vol - base_vol) / base_vol) * 100, 1)
                signals.append({
                    'signal_id': f'SIG-{q}-VOL-{as_of[11:16]}',
                    'incident_id': incident_id,
                    'metric': 'offered_volume',
                    'queue': q,
                    'observed_value': cur_vol,
                    'comparable_baseline': base_vol,
                    'deviation': rel_pct,
                    'unit': '%',
                    'severity': 'HIGH' if rel_pct > 25 else 'WATCH',
                })

            # AHT signal
            if base_aht > 0 and (cur_aht - base_aht) / base_aht > 0.10:
                rel_pct = round(((cur_aht - base_aht) / base_aht) * 100, 1)
                signals.append({
                    'signal_id': f'SIG-{q}-AHT-{as_of[11:16]}',
                    'incident_id': incident_id,
                    'metric': 'average_handle_time',
                    'queue': q,
                    'observed_value': round(cur_aht, 1),
                    'comparable_baseline': round(base_aht, 1),
                    'deviation': rel_pct,
                    'unit': '%',
                    'severity': 'HIGH' if rel_pct > 20 else 'WATCH',
                })

            # Staffing gap signal
            avail = int(row['available_agents'])
            req = int(row['required_agents'])
            if req > avail:
                signals.append({
                    'signal_id': f'SIG-{q}-STAFF-{as_of[11:16]}',
                    'incident_id': incident_id,
                    'metric': 'staffing_deficit',
                    'queue': q,
                    'observed_value': avail,
                    'comparable_baseline': req,
                    'deviation': req - avail,
                    'unit': 'agents',
                    'severity': 'CRITICAL' if (req - avail) >= 10 else 'HIGH' if (req - avail) >= 5 else 'WATCH',
                })

        return signals

    def advance_replay_timestamp(self, current_as_of: str, minutes: int = 30) -> str:
        """Advance replay clock by a discrete interval (default 30 mins) along the dataset."""
        cur_dt = pd.Timestamp(current_as_of)
        next_dt = cur_dt + timedelta(minutes=minutes)
        next_str = next_dt.strftime('%Y-%m-%d %H:%M:%S')

        # Check if next_str exists in dataset
        if next_str in self.df['timestamp'].values:
            return next_str
        return current_as_of

    def evaluate_replay_forecast_accuracy(
        self,
        queue: str,
        as_of: str,
        sla_floor: float = 0.75,
        max_lookahead_hours: float = 4.0
    ) -> Dict[str, Any]:
        """Evaluate early warning forecast accuracy against actual subsequent observations in dataset.
        Enforces clear separation between advance warning lead time and breach timing error.
        """
        ew = self.compute_early_warning_and_breach(queue, as_of, sla_floor=sla_floor)
        as_of_dt = pd.Timestamp(as_of)
        max_dt = as_of_dt + timedelta(hours=max_lookahead_hours)

        # Look forward in dataset for actual first observed breach
        future_rows = self.df[
            (self.df['queue'] == queue) &
            (pd.to_datetime(self.df['timestamp']) > as_of_dt) &
            (pd.to_datetime(self.df['timestamp']) <= max_dt)
        ].sort_values('timestamp')

        observed_breach_timestamp = None
        observed_lead_minutes = None

        for _, r in future_rows.iterrows():
            if float(r['sla']) < sla_floor:
                observed_breach_timestamp = str(r['timestamp'])
                observed_breach_dt = pd.Timestamp(observed_breach_timestamp)
                observed_lead_minutes = int((observed_breach_dt - as_of_dt).total_seconds() / 60.0)
                break

        predicted_breach_timestamp = ew.get('predicted_breach_timestamp')
        predicted_lead_minutes = ew.get('time_to_breach_minutes')

        timing_error_minutes = None
        if predicted_breach_timestamp and observed_breach_timestamp:
            pred_dt = pd.Timestamp(predicted_breach_timestamp)
            obs_dt = pd.Timestamp(observed_breach_timestamp)
            timing_error_minutes = abs(int((pred_dt - obs_dt).total_seconds() / 60.0))

        return {
            'queue': queue,
            'as_of': as_of,
            'predicted_breach': ew.get('predicted_breach', False),
            'predicted_breach_timestamp': predicted_breach_timestamp,
            'predicted_time_to_breach_minutes': predicted_lead_minutes,
            'observed_breach_timestamp': observed_breach_timestamp,
            'advance_warning_lead_minutes': observed_lead_minutes,
            'timing_error_minutes': timing_error_minutes,
            'calibration_note': (
                f"At {as_of[-8:-3]}, COIL gave {observed_lead_minutes}m advance warning before "
                f"the observed breach at {observed_breach_timestamp[-8:-3] if observed_breach_timestamp else 'N/A'}. "
                f"Predicted breach was {predicted_breach_timestamp[-8:-3] if predicted_breach_timestamp else 'N/A'}, "
                f"giving a timing error of {timing_error_minutes}m. "
                "Warning lead time and timing error are measured and reported separately."
            )
        }

