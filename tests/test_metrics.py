"""Test Suite for RG-03: Strict Business Metrics, Weighted KPIs, and Conservation."""
import pandas as pd
import pytest
from backend.business_metrics import (
    compute_weighted_kpis,
    verify_stock_flow_conservation,
    classify_sla_severity,
)


def test_weighted_kpis_normal():
    # Construct a sample multi-interval dataframe
    df = pd.DataFrame([
        {
            'timestamp': '2026-09-13 16:00:00',
            'offered_calls': 100,
            'answered_calls': 90,
            'abandoned_calls': 10,
            'sla_met_calls': 81,
            'sla': 0.90,
            'aht': 240.0,
            'available_agents': 20,
            'required_agents': 18,
            'occupancy': 0.60,
            'backlog': 5,
            'forecast': 95,
        },
        {
            'timestamp': '2026-09-13 16:30:00',
            'offered_calls': 200,
            'answered_calls': 180,
            'abandoned_calls': 20,
            'sla_met_calls': 144,
            'sla': 0.80,
            'aht': 300.0,
            'available_agents': 20,
            'required_agents': 25,
            'occupancy': 0.75,
            'backlog': 15,
            'forecast': 190,
        }
    ])

    kpis = compute_weighted_kpis(df)
    # Total offered: 300, Total answered: 270, Total abandoned: 30
    assert kpis['offered_calls'] == 300
    assert kpis['answered_calls'] == 270
    assert kpis['abandoned_calls'] == 30

    # Strict SLA: (81 + 144) / 270 = 225 / 270 = 0.8333...
    expected_sla = (81 + 144) / 270
    assert abs(kpis['sla'] - round(expected_sla, 4)) < 1e-4

    # Strict Abandon rate: (10 + 20) / 300 = 0.10
    assert abs(kpis['abandon_rate'] - 0.10) < 1e-4

    # Strict AHT: (240*90 + 300*180) / 270 = (21600 + 54000) / 270 = 75600 / 270 = 280.0s
    assert abs(kpis['aht'] - 280.0) < 1e-1

    # Closing backlog must be from the latest timestamp (15, NOT 5+15=20!)
    assert kpis['backlog'] == 15

    # WAPE forecast accuracy: 1 - (|95-100| + |190-200|) / 300 = 1 - (5 + 10)/300 = 1 - 0.05 = 0.95
    assert abs(kpis['forecast_accuracy'] - 0.95) < 1e-4


def test_weighted_kpis_empty():
    empty_df = pd.DataFrame()
    kpis = compute_weighted_kpis(empty_df)
    assert kpis['offered_calls'] == 0
    assert kpis['answered_calls'] == 0
    assert kpis['sla'] == 1.0
    assert kpis['backlog'] == 0
    assert kpis['forecast_accuracy'] == 1.0


def test_weighted_kpis_zero_answered():
    df = pd.DataFrame([{
        'timestamp': '2026-09-13 16:00:00',
        'offered_calls': 10,
        'answered_calls': 0,
        'abandoned_calls': 10,
        'sla_met_calls': 0,
        'sla': 0.0,
        'aht': 0.0,
        'available_agents': 5,
        'required_agents': 5,
        'occupancy': 0.0,
        'backlog': 0,
        'forecast': 10,
    }])
    kpis = compute_weighted_kpis(df)
    assert kpis['answered_calls'] == 0
    assert kpis['sla'] == 1.0  # Safe default when answered=0
    assert kpis['abandon_rate'] == 1.0
    assert kpis['aht'] == 0.0


def test_stock_flow_conservation():
    valid_row = {
        'backlog_opening': 10,
        'offered_calls': 50,
        'answered_calls': 45,
        'abandoned_calls': 5,
        'backlog': 10,
    }
    assert verify_stock_flow_conservation(valid_row) is True

    # 10 + 50 = 60, but answered(45) + abandoned(5) + closing(15) = 65 -> FAIL
    invalid_row = {
        'backlog_opening': 10,
        'offered_calls': 50,
        'answered_calls': 45,
        'abandoned_calls': 5,
        'backlog': 15,
    }
    assert verify_stock_flow_conservation(invalid_row) is False


def test_classify_sla_severity():
    assert classify_sla_severity(0.95) == 'NORMAL'
    assert classify_sla_severity(0.88) == 'WATCH'
    assert classify_sla_severity(0.80) == 'HIGH'
    assert classify_sla_severity(0.72) == 'CRITICAL'
    assert classify_sla_severity(0.95, active_incident=True) == 'WATCH'
