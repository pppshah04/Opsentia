"""Opsentia Business Metrics & Accounting Service.
Enforces strict mathematical definitions, stock-flow conservation,
and weighted KPI calculations without data leakage.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import pandas as pd


def compute_weighted_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute strictly weighted operational KPIs across a DataFrame of intervals.
    Avoids averaging percentages or summing closing stock.
    """
    if df.empty:
        return {
            'offered_calls': 0,
            'answered_calls': 0,
            'abandoned_calls': 0,
            'sla_met_calls': 0,
            'sla': 1.0,
            'abandon_rate': 0.0,
            'aht': 0.0,
            'total_handling_seconds': 0.0,
            'available_agents': 0.0,
            'required_agents': 0.0,
            'staffing_gap': 0.0,
            'occupancy': 0.0,
            'backlog': 0,
            'forecast_calls': 0,
            'forecast_accuracy': 1.0,
            'intervals_count': 0,
        }

    offered = float(df['offered_calls'].sum())
    answered = float(df['answered_calls'].sum())
    abandoned = float(df['abandoned_calls'].sum())
    sla_met = float(df['sla_met_calls'].sum())

    # SLA: sla_met / answered
    sla = (sla_met / answered) if answered > 0 else 1.0

    # Abandon rate: abandoned / offered
    abandon_rate = (abandoned / offered) if offered > 0 else 0.0

    # AHT: total handling seconds / answered
    # In synthetic_operations, aht is seconds per answered call for that interval
    total_handling_sec = float((df['aht'] * df['answered_calls']).sum())
    aht = (total_handling_sec / answered) if answered > 0 else 0.0

    # Available and required agents (mean across distinct timestamp intervals)
    ts_grouped = df.groupby('timestamp')[['available_agents', 'required_agents']].sum()
    avg_available = float(ts_grouped['available_agents'].mean()) if not ts_grouped.empty else 0.0
    avg_required = float(ts_grouped['required_agents'].mean()) if not ts_grouped.empty else 0.0
    staffing_gap = round(avg_required - avg_available, 1)

    # Occupancy: handling_seconds / (available_agent_minutes * 60)
    # Each available agent in a 30-min interval provides 1800 seconds of capacity
    total_available_seconds = float(df['available_agents'].sum()) * 1800.0
    if total_available_seconds > 0:
        occupancy = min(1.0, max(0.0, total_handling_sec / total_available_seconds))
    else:
        occupancy = 0.0

    # Backlog: closing stock for the final timestamp
    latest_ts = df['timestamp'].max()
    latest_df = df[df['timestamp'] == latest_ts]
    closing_backlog = int(latest_df['backlog'].sum())

    # Forecast accuracy: WAPE complement = 1 - sum(|forecast - offered|) / sum(offered)
    forecast_sum = float(df['forecast'].sum()) if 'forecast' in df.columns else 0.0
    if offered > 0 and 'forecast' in df.columns:
        wape_err = float((df['forecast'] - df['offered_calls']).abs().sum()) / offered
        forecast_acc = max(0.0, round(1.0 - wape_err, 4))
    else:
        forecast_acc = 1.0

    return {
        'offered_calls': int(offered),
        'answered_calls': int(answered),
        'abandoned_calls': int(abandoned),
        'sla_met_calls': int(sla_met),
        'sla': round(float(sla), 4),
        'abandon_rate': round(float(abandon_rate), 4),
        'aht': round(float(aht), 1),
        'total_handling_seconds': round(total_handling_sec, 1),
        'available_agents': round(avg_available, 1),
        'required_agents': round(avg_required, 1),
        'staffing_gap': staffing_gap,
        'occupancy': round(float(occupancy), 4),
        'backlog': closing_backlog,
        'forecast_calls': int(forecast_sum),
        'forecast_accuracy': forecast_acc,
        'intervals_count': int(df['timestamp'].nunique()),
    }


def verify_stock_flow_conservation(row: Dict[str, Any] | pd.Series) -> bool:
    """Check stock-flow conservation invariant:
    backlog_opening + offered == answered + abandoned + backlog_closing
    """
    opening = int(float(row['backlog_opening']))
    offered = int(float(row['offered_calls']))
    answered = int(float(row['answered_calls']))
    abandoned = int(float(row['abandoned_calls']))
    closing = int(float(row['backlog']))
    return (opening + offered) == (answered + abandoned + closing)


def classify_sla_severity(sla: float, active_incident: bool = False) -> str:
    """Classify SLA severity according to established operational bands:
    CRITICAL: < 0.75
    HIGH: < 0.85
    WATCH: < 0.90 or active warning
    NORMAL: >= 0.90
    """
    if sla < 0.75:
        return 'CRITICAL'
    if sla < 0.85:
        return 'HIGH'
    if sla < 0.90 or active_incident:
        return 'WATCH'
    return 'NORMAL'
