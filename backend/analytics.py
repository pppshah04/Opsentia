"""Opsentia — Analytics & Multi-Horizon Aggregation Service (v3.4)
Implements strictly prior, zero-leakage multi-horizon operational metrics (intraday, daily, weekly, monthly).
Recomputes partial current periods from raw 30-minute records to prevent future leakage.
Team VYRA · Google Cloud AI Builder Cup 2026.
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
from datetime import timedelta
import pandas as pd


def aggregate_queues_by_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    """Consolidate multiple queue rows at each timestamp into unified cross-queue records.
    Sums additive metrics (offered, answered, abandoned, sla_met, available_agents, backlog)
    and computes exact call-weighted SLA and AHT.
    """
    if df.empty or 'timestamp' not in df.columns:
        return df
    if df['timestamp'].nunique() == len(df):
        return df

    ts_order = df['timestamp'].drop_duplicates().tolist()
    work_df = df.copy()

    aht_col = 'aht' if 'aht' in work_df.columns else ('aht_seconds' if 'aht_seconds' in work_df.columns else None)
    if aht_col:
        work_df['_handle_sec'] = work_df['answered_calls'] * work_df[aht_col].fillna(0.0)
    else:
        work_df['_handle_sec'] = 0.0

    agents_col = 'available_agents' if 'available_agents' in work_df.columns else ('staffing_scheduled' if 'staffing_scheduled' in work_df.columns else None)
    backlog_col = 'backlog' if 'backlog' in work_df.columns else ('end_backlog' if 'end_backlog' in work_df.columns else None)

    agg_dict: Dict[str, Any] = {
        'offered_calls': 'sum',
        'answered_calls': 'sum',
        'abandoned_calls': 'sum',
        'sla_met_calls': 'sum',
        '_handle_sec': 'sum',
    }
    if agents_col:
        agg_dict[agents_col] = 'sum'
    if backlog_col:
        agg_dict[backlog_col] = 'sum'
    if 'date' in work_df.columns:
        agg_dict['date'] = 'first'
    if 'month' in work_df.columns:
        agg_dict['month'] = 'first'
    if 'iso_week' in work_df.columns:
        agg_dict['iso_week'] = 'first'

    grouped = work_df.groupby('timestamp', as_index=False).agg(agg_dict)

    # Compute consolidated AHT and SLA per interval
    grouped['sla'] = grouped.apply(
        lambda r: (r['sla_met_calls'] / r['answered_calls']) if r['answered_calls'] > 0 else 1.0,
        axis=1
    )
    grouped['aht'] = grouped.apply(
        lambda r: (r['_handle_sec'] / r['answered_calls']) if r['answered_calls'] > 0 else 0.0,
        axis=1
    )
    grouped['aht_seconds'] = grouped['aht']
    grouped['queue'] = 'All Queues'
    grouped.drop(columns=['_handle_sec'], inplace=True, errors='ignore')

    # Reorder according to original chronological timestamp order
    grouped['timestamp'] = pd.Categorical(grouped['timestamp'], categories=ts_order, ordered=True)
    grouped = grouped.sort_values('timestamp').reset_index(drop=True)
    grouped['timestamp'] = grouped['timestamp'].astype(str)
    return grouped


def compute_weighted_slice(df_slice: pd.DataFrame) -> Dict[str, Any]:
    """Compute exact call-weighted KPIs over a filtered dataframe slice."""
    if df_slice.empty:
        return {
            'offered_calls': 0,
            'answered_calls': 0,
            'abandoned_calls': 0,
            'sla_met_calls': 0,
            'sla': None,
            'sla_pct': None,
            'abandon_rate': None,
            'abandon_rate_pct': None,
            'aht_seconds': None,
            'avg_available_agents': 0.0,
            'end_backlog': 0,
            'peak_backlog': 0,
            'intervals_observed': 0,
        }

    # If df_slice contains multi-queue unaggregated rows, pre-aggregate per timestamp
    if 'timestamp' in df_slice.columns and df_slice['timestamp'].nunique() < len(df_slice):
        df_slice = aggregate_queues_by_timestamp(df_slice)

    offered = int(df_slice['offered_calls'].sum())
    answered = int(df_slice['answered_calls'].sum())
    abandoned = int(df_slice['abandoned_calls'].sum())
    sla_met = int(df_slice['sla_met_calls'].sum())
    
    sla = (sla_met / answered) if answered > 0 else None
    abandon_rate = (abandoned / offered) if offered > 0 else None
    
    # Handle time / AHT weighting
    if 'aht' in df_slice.columns and answered > 0:
        total_handle_sec = float((df_slice['answered_calls'] * df_slice['aht']).sum())
        aht = total_handle_sec / answered
    elif 'aht_seconds' in df_slice.columns and answered > 0:
        total_handle_sec = float((df_slice['answered_calls'] * df_slice['aht_seconds']).sum())
        aht = total_handle_sec / answered
    else:
        aht = None

    # Staffing / capacity weighting (mean across discrete interval timestamps)
    agents_col = 'available_agents' if 'available_agents' in df_slice.columns else ('staffing_scheduled' if 'staffing_scheduled' in df_slice.columns else None)
    avg_agents = float(df_slice[agents_col].mean()) if agents_col and not df_slice[agents_col].empty else 0.0

    # Backlog stock-flow: end backlog is closing backlog at final interval; peak backlog is maximum combined interval backlog
    backlog_col = 'backlog' if 'backlog' in df_slice.columns else ('end_backlog' if 'end_backlog' in df_slice.columns else None)
    if backlog_col:
        end_backlog = int(df_slice[backlog_col].iloc[-1])
        peak_backlog = int(df_slice[backlog_col].max())
    else:
        end_backlog = 0
        peak_backlog = 0

    return {
        'offered_calls': offered,
        'answered_calls': answered,
        'abandoned_calls': abandoned,
        'sla_met_calls': sla_met,
        'sla': round(sla, 4) if sla is not None else None,
        'sla_pct': round(sla * 100, 2) if sla is not None else None,
        'abandon_rate': round(abandon_rate, 4) if abandon_rate is not None else None,
        'abandon_rate_pct': round(abandon_rate * 100, 2) if abandon_rate is not None else None,
        'aht_seconds': round(aht, 1) if aht is not None else None,
        'avg_available_agents': round(avg_agents, 1),
        'end_backlog': end_backlog,
        'peak_backlog': peak_backlog,
        'intervals_observed': len(df_slice),
    }


class OpsentiaAnalyticsService:
    """Multi-horizon analytical query service with strict temporal cutoff."""

    def __init__(self, ops_df: pd.DataFrame):
        self.raw_df = ops_df.copy()
        # Ensure timestamp sorting
        self.raw_df = self.raw_df.sort_values('timestamp').reset_index(drop=True)
        # Pre-extract dates for high-performance slicing
        self.raw_df['date'] = self.raw_df['timestamp'].str.slice(0, 10)
        self.raw_df['month'] = self.raw_df['timestamp'].str.slice(0, 7)
        self.raw_df['iso_week'] = pd.to_datetime(self.raw_df['date']).dt.strftime('%G-W%V')

    def get_analytics(
        self,
        queue: str = 'Queue A',
        grain: str = 'intraday',
        as_of: str = '2026-09-13 16:30:00',
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        lookback: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Query metrics at requested granularity strictly through as_of."""
        # 1. Scope raw records strictly through as_of (zero future leakage)
        cutoff_df = self.raw_df[self.raw_df['timestamp'] <= as_of]
        if queue != 'All Queues':
            cutoff_df = cutoff_df[cutoff_df['queue'] == queue]
        else:
            cutoff_df = aggregate_queues_by_timestamp(cutoff_df)

        grain = grain.lower().strip()
        as_of_dt = pd.Timestamp(as_of)
        current_day = as_of[:10]
        current_iso_week = as_of_dt.strftime('%G-W%V')
        current_month = as_of[:7]

        warnings: List[str] = []

        if grain == 'intraday':
            target_date = from_date or current_day
            day_slice = cutoff_df[cutoff_df['date'] == target_date]
            is_partial = bool(target_date == current_day and as_of[11:16] < '23:30')
            if is_partial:
                warnings.append(f'Partial intraday observed: {len(day_slice)}/48 intervals elapsed as of {as_of[11:16]}.')

            series = []
            for r in day_slice.itertuples():
                sla_val = (r.sla_met_calls / r.answered_calls) if r.answered_calls > 0 else None
                series.append({
                    'period': r.timestamp[11:16],
                    'time': r.timestamp[11:16],
                    'timestamp': r.timestamp,
                    'offered_calls': int(r.offered_calls),
                    'answered_calls': int(r.answered_calls),
                    'abandoned_calls': int(r.abandoned_calls),
                    'sla': round(sla_val, 4) if sla_val is not None else None,
                    'sla_pct': round(sla_val * 100, 1) if sla_val is not None else None,
                    'aht': round(float(r.aht), 1) if hasattr(r, 'aht') else None,
                    'available_agents': int(r.available_agents),
                    'backlog': int(r.backlog),
                    'is_partial': False,
                })

            summary = compute_weighted_slice(day_slice)

            # Compare to previous day at same time
            prev_day_str = (pd.Timestamp(target_date) - timedelta(days=1)).strftime('%Y-%m-%d')
            prev_slice = self.raw_df[
                (self.raw_df['date'] == prev_day_str) &
                (self.raw_df['timestamp'] <= f'{prev_day_str} {as_of[11:19]}') &
                ((self.raw_df['queue'] == queue) if queue != 'All Queues' else True)
            ]
            if queue == 'All Queues':
                prev_slice = aggregate_queues_by_timestamp(prev_slice)
            prev_summary = compute_weighted_slice(prev_slice)

            comparison = self._build_comparison(summary, prev_summary, label="Prior Day Same Interval")

            return {
                'queue': queue,
                'grain': 'intraday',
                'as_of': as_of,
                'period_start': f'{target_date} 00:00:00',
                'period_end': as_of if target_date == current_day else f'{target_date} 23:30:00',
                'is_partial': is_partial,
                'summary': summary,
                'comparison': comparison,
                'series': series,
                'periods': series,
                'warnings': warnings,
            }

        elif grain == 'day' or grain == 'daily':
            # Last 30 available days through as_of
            unique_days = sorted(cutoff_df['date'].unique().tolist())
            if from_date:
                unique_days = [d for d in unique_days if d >= from_date]
            if to_date:
                unique_days = [d for d in unique_days if d <= to_date]
            elif lookback:
                unique_days = unique_days[-lookback:]
            else:
                unique_days = unique_days[-30:]

            series = []
            for d_str in unique_days:
                d_slice = cutoff_df[cutoff_df['date'] == d_str]
                d_summary = compute_weighted_slice(d_slice)
                d_partial = bool(d_str == current_day and as_of[11:16] < '23:30')
                series.append({
                    'period': d_str,
                    'date': d_str,
                    'offered_calls': d_summary['offered_calls'],
                    'answered_calls': d_summary['answered_calls'],
                    'abandoned_calls': d_summary['abandoned_calls'],
                    'sla': d_summary['sla'],
                    'sla_pct': d_summary['sla_pct'],
                    'aht': d_summary['aht_seconds'],
                    'aht_seconds': d_summary['aht_seconds'],
                    'avg_agents': d_summary['avg_available_agents'],
                    'end_backlog': d_summary['end_backlog'],
                    'intervals_included': len(d_slice),
                    'is_partial': d_partial,
                })

            is_partial = bool(as_of[11:16] < '23:30')
            if is_partial:
                warnings.append(f'Current day {current_day} is partial (as of {as_of[11:16]}).')

            cur_day_slice = cutoff_df[cutoff_df['date'] == current_day]
            summary = compute_weighted_slice(cur_day_slice)

            # Compare to previous calendar day
            if len(unique_days) >= 2:
                prev_d_str = unique_days[-2]
                prev_slice = cutoff_df[cutoff_df['date'] == prev_d_str]
                prev_summary = compute_weighted_slice(prev_slice)
            else:
                prev_summary = compute_weighted_slice(pd.DataFrame())

            comparison = self._build_comparison(summary, prev_summary, label="Prior Completed Day")

            return {
                'queue': queue,
                'grain': 'day',
                'as_of': as_of,
                'period_start': unique_days[0] if unique_days else current_day,
                'period_end': current_day,
                'is_partial': is_partial,
                'summary': summary,
                'comparison': comparison,
                'series': series,
                'periods': series,
                'warnings': warnings,
            }

        elif grain == 'week' or grain == 'weekly':
            lookback_w = lookback or 12
            unique_weeks = sorted(cutoff_df['iso_week'].unique().tolist())[-lookback_w:]
            series = []
            for w_str in unique_weeks:
                w_slice = cutoff_df[cutoff_df['iso_week'] == w_str]
                w_summary = compute_weighted_slice(w_slice)
                w_partial = bool(w_str == current_iso_week and (as_of_dt.weekday() < 6 or as_of[11:16] < '23:30'))
                series.append({
                    'period': w_str,
                    'iso_week': w_str,
                    'offered_calls': w_summary['offered_calls'],
                    'answered_calls': w_summary['answered_calls'],
                    'abandoned_calls': w_summary['abandoned_calls'],
                    'sla': w_summary['sla'],
                    'sla_pct': w_summary['sla_pct'],
                    'aht': w_summary['aht_seconds'],
                    'avg_agents': w_summary['avg_available_agents'],
                    'end_backlog': w_summary['end_backlog'],
                    'is_partial': w_partial,
                })

            is_partial = bool(as_of_dt.weekday() < 6 or as_of[11:16] < '23:30')
            if is_partial:
                warnings.append(f'Current week {current_iso_week} is incomplete (weekday {as_of_dt.strftime("%A")} elapsed through {as_of[11:16]}).')

            cur_week_slice = cutoff_df[cutoff_df['iso_week'] == current_iso_week]
            summary = compute_weighted_slice(cur_week_slice)

            if len(unique_weeks) >= 2:
                prev_w_str = unique_weeks[-2]
                prev_slice = cutoff_df[cutoff_df['iso_week'] == prev_w_str]
                prev_summary = compute_weighted_slice(prev_slice)
            else:
                prev_summary = compute_weighted_slice(pd.DataFrame())

            comparison = self._build_comparison(summary, prev_summary, label="Prior Completed Week")

            return {
                'queue': queue,
                'grain': 'week',
                'as_of': as_of,
                'period_start': unique_weeks[0] if unique_weeks else current_iso_week,
                'period_end': current_iso_week,
                'is_partial': is_partial,
                'summary': summary,
                'comparison': comparison,
                'series': series,
                'periods': series,
                'warnings': warnings,
            }

        elif grain == 'month' or grain == 'monthly':
            lookback_m = lookback or 12
            unique_months = sorted(cutoff_df['month'].unique().tolist())[-lookback_m:]
            series = []
            for m_str in unique_months:
                m_slice = cutoff_df[cutoff_df['month'] == m_str]
                m_summary = compute_weighted_slice(m_slice)
                m_partial = bool(m_str == current_month and (as_of_dt.day < 30 or as_of[11:16] < '23:30'))
                series.append({
                    'period': m_str,
                    'month': m_str,
                    'offered_calls': m_summary['offered_calls'],
                    'answered_calls': m_summary['answered_calls'],
                    'abandoned_calls': m_summary['abandoned_calls'],
                    'sla': m_summary['sla'],
                    'sla_pct': m_summary['sla_pct'],
                    'aht': m_summary['aht_seconds'],
                    'avg_agents': m_summary['avg_available_agents'],
                    'end_backlog': m_summary['end_backlog'],
                    'is_partial': m_partial,
                })

            is_partial = bool(as_of_dt.day < 30 or as_of[11:16] < '23:30')
            if is_partial:
                warnings.append(f'Current month {current_month} is partial (day {as_of_dt.day} elapsed through {as_of[11:16]}).')

            cur_m_slice = cutoff_df[cutoff_df['month'] == current_month]
            summary = compute_weighted_slice(cur_m_slice)

            if len(unique_months) >= 2:
                prev_m_str = unique_months[-2]
                prev_slice = cutoff_df[cutoff_df['month'] == prev_m_str]
                prev_summary = compute_weighted_slice(prev_slice)
            else:
                prev_summary = compute_weighted_slice(pd.DataFrame())

            comparison = self._build_comparison(summary, prev_summary, label="Prior Completed Month")

            return {
                'queue': queue,
                'grain': 'month',
                'as_of': as_of,
                'period_start': unique_months[0] if unique_months else current_month,
                'period_end': current_month,
                'is_partial': is_partial,
                'summary': summary,
                'comparison': comparison,
                'series': series,
                'periods': series,
                'warnings': warnings,
            }

        else:
            raise ValueError(f"Unsupported grain: {grain}. Must be one of 'intraday', 'day', 'week', 'month'.")

    def _build_comparison(self, current: Dict[str, Any], prior: Dict[str, Any], label: str) -> Dict[str, Any]:
        """Compute differences between current and prior period."""
        cur_sla = current.get('sla')
        pri_sla = prior.get('sla')
        sla_delta_pp = round((cur_sla - pri_sla) * 100, 2) if (cur_sla is not None and pri_sla is not None) else None

        cur_vol = current.get('offered_calls', 0)
        pri_vol = prior.get('offered_calls', 0)
        vol_change_pct = round(((cur_vol - pri_vol) / pri_vol) * 100, 1) if pri_vol > 0 else None

        cur_aht = current.get('aht_seconds')
        pri_aht = prior.get('aht_seconds')
        aht_delta_sec = round(cur_aht - pri_aht, 1) if (cur_aht is not None and pri_aht is not None) else None

        return {
            'comparison_label': label,
            'prior_period_sla': pri_sla,
            'prior_period_sla_pct': round(pri_sla * 100, 1) if pri_sla is not None else None,
            'sla_delta_pp': sla_delta_pp,
            'prior_period_volume': pri_vol,
            'volume_change_pct': vol_change_pct,
            'prior_period_aht': pri_aht,
            'aht_delta_sec': aht_delta_sec,
        }
