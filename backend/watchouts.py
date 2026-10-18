"""Opsentia — AI Watch-Outs Engine (v3.4)
Detects and ranks operational watch-outs across Intraday, Daily, Weekly, and Monthly horizons.
Derives all metrics, deltas, staffing requirements, and monthly volume dynamically from data and policy tables.
Team VYRA · Google Cloud AI Builder Cup 2026.
"""
from __future__ import annotations
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd


class OpsentiaWatchoutsService:
    """Multi-horizon operational watch-outs generator."""

    def __init__(
        self,
        ops_df: pd.DataFrame,
        analytics_service,
        forecast_service,
        policies_df: Optional[pd.DataFrame] = None,
    ):
        self.ops_df = ops_df
        self.analytics = analytics_service
        self.forecast = forecast_service

        if policies_df is not None:
            self.policies_df = policies_df.copy()
        else:
            candidate_paths = [
                Path('data/opsentia_metric_policies.csv'),
                Path(__file__).parent.parent / 'data' / 'opsentia_metric_policies.csv',
            ]
            loaded = False
            for p in candidate_paths:
                if p.exists():
                    try:
                        self.policies_df = pd.read_csv(p)
                        loaded = True
                        break
                    except Exception:
                        pass
            if not loaded:
                self.policies_df = pd.DataFrame()

    def _get_policy(self, metric: str) -> Dict[str, Any]:
        """Fetch metric policy thresholds dynamically from policy table."""
        if not self.policies_df.empty and 'metric' in self.policies_df.columns:
            m_row = self.policies_df[self.policies_df['metric'] == metric]
            if not m_row.empty:
                r = m_row.iloc[0]
                return {
                    'target': float(r['target_value']) if pd.notna(r.get('target_value')) else None,
                    'watch': float(r['watch_boundary']) if pd.notna(r.get('watch_boundary')) else None,
                    'high': float(r['high_boundary']) if pd.notna(r.get('high_boundary')) else None,
                    'critical': float(r['critical_boundary']) if pd.notna(r.get('critical_boundary')) else None,
                    'tolerance': float(r['historical_tolerance_fraction']) if pd.notna(r.get('historical_tolerance_fraction')) else 0.10,
                }
        defaults = {
            'sla': {'target': 0.90, 'watch': 0.90, 'high': 0.85, 'critical': 0.75, 'tolerance': 0.05},
            'occupancy': {'target': 0.85, 'watch': 0.88, 'high': 0.93, 'critical': 0.97, 'tolerance': 0.04},
            'aht': {'target': None, 'watch': None, 'high': None, 'critical': None, 'tolerance': 0.10},
        }
        return defaults.get(metric, {'target': None, 'watch': None, 'high': None, 'critical': None, 'tolerance': 0.10})

    def get_watchouts(
        self,
        queue: str = 'Queue A',
        as_of: str = '2026-09-13 16:30:00',
        horizon: str = 'all',
    ) -> List[Dict[str, Any]]:
        """Generate prioritised, grounded operational watch-outs for the selected queue and horizon."""
        horizon = horizon.lower().strip()
        as_of_dt = pd.Timestamp(as_of)

        watchouts: List[Dict[str, Any]] = []

        # ----------------------------------------------------
        # 1. INTRADAY WATCH-OUTS
        # ----------------------------------------------------
        if horizon in ('all', 'intraday'):
            intra = self.analytics.get_analytics(queue=queue, grain='intraday', as_of=as_of)
            series = intra.get('series', [])
            if series:
                latest = series[-1]
                cur_sla = latest.get('sla_pct')
                cur_backlog = latest.get('backlog', 0)
                cur_aht = latest.get('aht', 0) or 280.0
                cur_agents = latest.get('available_agents', 0)
                cur_offered = latest.get('offered_calls', 0)
                cur_answered = latest.get('answered_calls', 0)
                cur_sla_met = latest.get('sla_met_calls', 0)

                sla_pol = self._get_policy('sla')
                target_sla_pct = (sla_pol['target'] or 0.90) * 100.0
                watch_sla_pct = (sla_pol['watch'] or 0.90) * 100.0
                high_sla_pct = (sla_pol['high'] or 0.85) * 100.0
                crit_sla_pct = (sla_pol['critical'] or 0.75) * 100.0

                # A. Capacity Pressure / SLA Dip
                if cur_sla is not None and cur_sla < watch_sla_pct:
                    severity = 'CRITICAL' if cur_sla < crit_sla_pct else ('HIGH' if cur_sla < high_sla_pct else 'WATCH')

                    # Compute dynamic delta from previous 30m interval
                    prev_sla = series[-2].get('sla_pct') if len(series) >= 2 else None
                    if prev_sla is not None:
                        delta_sla = round(cur_sla - prev_sla, 1)
                        if delta_sla < 0:
                            trajectory = f"Deteriorating ({delta_sla:+.1f} pp in last 30m)"
                        elif delta_sla > 0:
                            trajectory = f"Recovering ({delta_sla:+.1f} pp in last 30m)"
                        else:
                            trajectory = "Stable across consecutive intervals"
                    else:
                        trajectory = "Initial observation against policy baseline"

                    # Calculate dynamically required staffing
                    target_met_calls = int(round(cur_offered * (target_sla_pct / 100.0)))
                    deficit_calls = max(0, target_met_calls - cur_sla_met)
                    calls_per_agent = max(0.1, (1800.0 / max(30.0, cur_aht)) * 0.90)
                    agents_needed = max(1, math.ceil(deficit_calls / calls_per_agent))

                    watchouts.append({
                        'watchout_id': f'WO-INTRA-{queue[:3].upper()}-01',
                        'horizon': 'intraday',
                        'severity': severity,
                        'metric': 'SLA',
                        'queue': queue,
                        'first_seen': latest.get('timestamp', as_of),
                        'observed': f'{cur_sla}%',
                        'expected_historical': f'{target_sla_pct}% SLA Target',
                        'trajectory': trajectory,
                        'projected_next': f'Sub-{int(cur_sla)}% sustained SLA breach risk without mitigation',
                        'reason': f'Queue {queue} interval SLA dropped to {cur_sla}% under offered volume of {cur_offered} calls.',
                        'evidence_ids': [f'SRC-OPS-{queue}-{latest.get("timestamp", as_of)}'],
                        'recommended_review': f'Evaluate Decision Lab mitigation scenario: add +{agents_needed} temporary agents or initiate donor transfer under 85.0% protected floor.',
                        'owner': 'Real-Time Operations Lead',
                        'data_origin': 'SYNTHETIC_REPLAY',
                        'ai_mode': 'COIL_DETERMINISTIC_EVIDENCE',
                    })

                # B. Elevated AHT / Occupancy Surge
                occ_pol = self._get_policy('occupancy')
                watch_occ_pct = (occ_pol['watch'] or 0.88) * 100.0
                high_occ_pct = (occ_pol['high'] or 0.93) * 100.0
                crit_occ_pct = (occ_pol['critical'] or 0.97) * 100.0

                obs_occupancy = round((cur_answered * cur_aht) / (cur_agents * 1800.0) * 100.0, 1) if (cur_agents > 0 and cur_aht > 0) else None

                if obs_occupancy is not None and obs_occupancy >= watch_occ_pct:
                    occ_severity = 'CRITICAL' if obs_occupancy >= crit_occ_pct else ('HIGH' if obs_occupancy >= high_occ_pct else 'WATCH')
                    watchouts.append({
                        'watchout_id': f'WO-INTRA-{queue[:3].upper()}-02',
                        'horizon': 'intraday',
                        'severity': occ_severity,
                        'metric': 'Occupancy',
                        'queue': queue,
                        'first_seen': latest.get('timestamp', as_of),
                        'observed': f'{obs_occupancy}%',
                        'expected_historical': f'{(occ_pol["target"] or 0.85)*100.0}% Target',
                        'trajectory': f'{round(obs_occupancy - (occ_pol["target"] or 0.85)*100.0, 1):+.1f} pp over target',
                        'projected_next': f'Interval agent workload density at {obs_occupancy}%',
                        'reason': f'Elevated handle time ({cur_aht}s) and call demand driving interval occupancy to {obs_occupancy}%.',
                        'evidence_ids': [f'SRC-OPS-{queue}-{latest.get("timestamp", as_of)}'],
                        'recommended_review': 'Review frontline agent wrap-up guidance and check for complex tier-2 transfers.',
                        'owner': 'Queue Supervisor',
                        'data_origin': 'SYNTHETIC_REPLAY',
                        'ai_mode': 'COIL_DETERMINISTIC_EVIDENCE',
                    })
                elif cur_aht > 300.0:
                    watchouts.append({
                        'watchout_id': f'WO-INTRA-{queue[:3].upper()}-02',
                        'horizon': 'intraday',
                        'severity': 'WATCH',
                        'metric': 'AHT',
                        'queue': queue,
                        'first_seen': latest.get('timestamp', as_of),
                        'observed': f'{cur_aht}s',
                        'expected_historical': '280.0s Baseline',
                        'trajectory': f'+{round(cur_aht - 280.0, 1)}s elongation',
                        'projected_next': 'Occupancy elevated in upcoming peak intervals',
                        'reason': 'Extended handle times reducing interval agent turnaround capacity.',
                        'evidence_ids': [f'SRC-OPS-{queue}-{latest.get("timestamp", as_of)}'],
                        'recommended_review': 'Review frontline agent wrap-up guidance and check for complex tier-2 transfers.',
                        'owner': 'Queue Supervisor',
                        'data_origin': 'SYNTHETIC_REPLAY',
                        'ai_mode': 'COIL_DETERMINISTIC_EVIDENCE',
                    })

        # ----------------------------------------------------
        # 2. DAILY WATCH-OUTS
        # ----------------------------------------------------
        if horizon in ('all', 'daily', 'day'):
            fc = self.forecast.get_full_day_forecast(queue=queue, as_of=as_of)
            p_full = fc.get('projected_full_day', {})
            eod_sla = p_full.get('sla_pct')
            target_sla_pct = fc.get('target_sla_pct', 90.0)
            eod_breach = p_full.get('target_breached', False)

            if eod_breach or (eod_sla is not None and eod_sla < target_sla_pct):
                rem_intervals = fc.get('predicted_remaining', {}).get('intervals_count', 0)
                rem_offered = fc.get('predicted_remaining', {}).get('offered_calls', 0)
                rem_sla_met = fc.get('predicted_remaining', {}).get('sla_met_calls', 0)
                target_met = int(round(rem_offered * (target_sla_pct / 100.0)))
                deficit_calls = max(0, target_met - rem_sla_met)
                aht_sec = p_full.get('aht_seconds') or 280.0
                calls_per_agent_int = max(0.1, (1800.0 / aht_sec) * 0.90)
                agents_needed = max(1, math.ceil(deficit_calls / (calls_per_agent_int * max(1, rem_intervals)))) if rem_intervals > 0 else 1

                watchouts.append({
                    'watchout_id': f'WO-DAY-{queue[:3].upper()}-01',
                    'horizon': 'daily',
                    'severity': 'HIGH' if (eod_sla and eod_sla < 85.0) else 'WATCH',
                    'metric': 'EOD SLA',
                    'queue': queue,
                    'first_seen': as_of,
                    'observed': f"{fc.get('actual_to_date', {}).get('sla_pct', 0)}% (to date)",
                    'expected_historical': f'{target_sla_pct}% Daily SLA Target',
                    'trajectory': f"Projected EOD SLA {eod_sla}% (Risk: {p_full.get('risk_level', 'NORMAL')}, Range: {p_full.get('sla_lower_pct')}–{p_full.get('sla_upper_pct')}%)",
                    'projected_next': f"End of operating day deficit across remaining {rem_intervals} intervals",
                    'reason': f"Forecasted remaining volume requires average +{agents_needed} agents above baseline across {rem_intervals} remaining intervals to preserve {target_sla_pct}% SLA.",
                    'evidence_ids': [f'SRC-FC-{queue}-{as_of}'],
                    'recommended_review': 'Activate shift overtime extension or reallocate donor queue capacity.',
                    'owner': 'Operations Director',
                    'data_origin': 'SYNTHETIC_REPLAY',
                    'ai_mode': 'COIL_EOD_FORECAST_EVIDENCE',
                })
            else:
                watchouts.append({
                    'watchout_id': f'WO-DAY-{queue[:3].upper()}-02',
                    'horizon': 'daily',
                    'severity': 'NORMAL',
                    'metric': 'EOD SLA',
                    'queue': queue,
                    'first_seen': as_of,
                    'observed': f"{fc.get('actual_to_date', {}).get('sla_pct', 0)}% (to date)",
                    'expected_historical': f'{target_sla_pct}% Daily Target',
                    'trajectory': f"Projected EOD {eod_sla}% (Target Maintained)",
                    'projected_next': 'Full day expected to conclude within operational service commitment',
                    'reason': f"Cumulative answered calls to date provide sufficient margin against remaining {fc.get('predicted_remaining', {}).get('intervals_count', 0)} intervals.",
                    'evidence_ids': [f'SRC-FC-{queue}-{as_of}'],
                    'recommended_review': 'Maintain standard scheduled capacity rosters.',
                    'owner': 'Workforce Management',
                    'data_origin': 'SYNTHETIC_REPLAY',
                    'ai_mode': 'COIL_EOD_FORECAST_EVIDENCE',
                })

        # ----------------------------------------------------
        # 3. WEEKLY WATCH-OUTS
        # ----------------------------------------------------
        if horizon in ('all', 'weekly', 'week'):
            week_data = self.analytics.get_analytics(queue=queue, grain='week', as_of=as_of)
            comp = week_data.get('comparison', {})
            sla_delta = comp.get('sla_delta_pp')
            vol_change = comp.get('volume_change_pct', 0.0)
            staffing_change = comp.get('staffing_change_pct', 0.0)

            if sla_delta is not None and sla_delta < -1.5:
                watchouts.append({
                    'watchout_id': f'WO-WEEK-{queue[:3].upper()}-01',
                    'horizon': 'weekly',
                    'severity': 'WATCH',
                    'metric': 'Weekly SLA Trend',
                    'queue': queue,
                    'first_seen': as_of[:10],
                    'observed': f"{week_data.get('summary', {}).get('sla_pct', 0)}%",
                    'expected_historical': f"{comp.get('prior_period_sla_pct', 0)}% (Prior Week)",
                    'trajectory': f"{sla_delta:+.1f} pp week-over-week change",
                    'projected_next': 'Potential consecutive weekly breach if peak interval staffing is not adjusted',
                    'reason': f"Workload volume shifted by {vol_change:+.1f}% while average staffing changed by {staffing_change:+.1f}% vs prior week.",
                    'evidence_ids': [f"SRC-KPI-WEEK-{week_data.get('period_end', '')}"],
                    'recommended_review': 'Rebalance intra-week staffing distribution between peak arrival days.',
                    'owner': 'Capacity Planning Lead',
                    'data_origin': 'SYNTHETIC_REPLAY',
                    'ai_mode': 'COIL_TREND_ANALYTICS',
                })

        # ----------------------------------------------------
        # 4. MONTHLY WATCH-OUTS
        # ----------------------------------------------------
        if horizon in ('all', 'monthly', 'month'):
            month_data = self.analytics.get_analytics(queue=queue, grain='month', as_of=as_of)
            summary = month_data.get('summary', {})
            total_offered = summary.get('offered_calls', 0)
            day_of_month = as_of_dt.day
            days_in_month = as_of_dt.days_in_month

            # Calendar-grounded monthly volume projection based on actual elapsed days
            proj_vol = int(round(total_offered * (days_in_month / max(1, day_of_month))))

            watchouts.append({
                'watchout_id': f'WO-MONTH-{queue[:3].upper()}-01',
                'horizon': 'monthly',
                'severity': 'NORMAL' if (summary.get('sla_pct') or 100) >= 90.0 else 'WATCH',
                'metric': 'Monthly Service Commitment',
                'queue': queue,
                'first_seen': as_of[:7],
                'observed': f"{summary.get('sla_pct', 0)}% MTD",
                'expected_historical': '90.0% Enterprise Objective',
                'trajectory': f"Tracking at {summary.get('sla_pct', 0)}% MTD across {day_of_month}/{days_in_month} elapsed days",
                'projected_next': f"Total expected monthly volume ~{proj_vol:,} calls (extrapolated from {day_of_month}/{days_in_month} elapsed days)",
                'reason': f"Month-to-date offered volume is {total_offered:,} calls across {day_of_month} elapsed days with SLA at {summary.get('sla_pct', 0)}%.",
                'evidence_ids': [f"SRC-KPI-MONTH-{as_of[:7]}"],
                'recommended_review': 'Include in monthly executive operational review.',
                'owner': 'Operations Vice President',
                'data_origin': 'SYNTHETIC_REPLAY',
                'ai_mode': 'COIL_TREND_ANALYTICS',
            })

        return watchouts

    generate_watchouts = get_watchouts
