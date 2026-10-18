"""Test Suite for RG-04, RG-05, and RG-06: COIL Engine, Zero-Leakage Baselines,
Early Warning Lead Time, and Incident Fusion.
"""
from pathlib import Path
import pandas as pd
import pytest
from backend.coil import CoilEngine
from backend.incidents import IncidentLifecycleService

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
ops_df = pd.read_csv(DATA / 'synthetic_operations.csv', low_memory=False)


def test_no_future_leakage_in_baseline():
    """RG-04: Baseline computation at as_of MUST only contain prior timestamps."""
    engine = CoilEngine(ops_df)
    as_of = '2026-09-13 16:30:00'
    base = engine.get_prior_baseline('Queue A', as_of, lookback_weeks=4)

    assert base['sample_count'] == 4
    for ts in base['timestamps_used']:
        assert ts < as_of, f"Future leakage detected: {ts} is >= {as_of}"
        assert ts.endswith('16:30:00'), f"Baseline slot mismatch: {ts}"
        # Same day of week as 2026-09-13 (Sunday)
        assert pd.Timestamp(ts).dayofweek == pd.Timestamp(as_of).dayofweek


def test_early_warning_leads_observed_breach():
    """RG-05: At 16:30, Queue A is degraded but above floor; warning issued with 30m lead time.
    At 17:00, actual floor breach (< 0.75) is observed.
    """
    engine = CoilEngine(ops_df)

    # 1. Inspect state at 16:30 (pre-breach interval)
    pre_as_of = '2026-09-13 16:30:00'
    pre_ew = engine.compute_early_warning_and_breach('Queue A', pre_as_of, sla_floor=0.75)

    assert pre_ew['current_sla'] > 0.75, "At 16:30, SLA should still be above 0.75 floor"
    assert pre_ew['is_observed_breach'] is False, "Floor breach should NOT yet be observed at 16:30"
    assert pre_ew['state'] in ('WATCH', 'HIGH'), f"Expected early warning state, got {pre_ew['state']}"
    assert pre_ew['predicted_breach'] is True, "Expected breach prediction at 16:30"
    assert pre_ew['time_to_breach_minutes'] in (30, 45, 60), f"Expected 30-60m lead time, got {pre_ew['time_to_breach_minutes']}"

    # 2. Advance replay to 17:00 (breach interval)
    breach_as_of = engine.advance_replay_timestamp(pre_as_of, minutes=30)
    assert breach_as_of == '2026-09-13 17:00:00'

    breach_ew = engine.compute_early_warning_and_breach('Queue A', breach_as_of, sla_floor=0.75)
    assert breach_ew['current_sla'] < 0.75, "At 17:00, SLA should be below 0.75 floor"
    assert breach_ew['is_observed_breach'] is True, "Floor breach must be observed at 17:00"
    assert breach_ew['state'] == 'CRITICAL'


def test_incident_fusion_correlates_signals():
    """RG-06: Related operational signals (SLA, Volume, Staffing) fuse under one incident."""
    engine = CoilEngine(ops_df)
    as_of = '2026-09-13 16:30:00'
    incident_id = 'EV-2026-0913-01'

    signals = engine.correlate_incident_signals(incident_id, as_of)
    assert len(signals) >= 2, "Expected at least 2 correlating operational signals"

    # Verify signals include service level and staffing deficit
    metrics_found = {s['metric'] for s in signals}
    assert 'service_level' in metrics_found
    assert 'staffing_deficit' in metrics_found
    for s in signals:
        assert s['incident_id'] == incident_id


def test_incident_lifecycle_hysteresis():
    """RG-06: Hysteresis prevents flapping: 2 consecutive normal intervals needed to resolve."""
    inc_service = IncidentLifecycleService(DATA)
    iid = 'EV-TEST-001'

    # Step 1: SLA drops to 0.70 -> immediately CRITICAL
    inc1 = inc_service.update_incident_state(iid, current_sla=0.70, as_of='2026-09-13 17:00:00')
    assert inc1['state'] == 'CRITICAL'

    # Step 2: One good interval at 0.92 -> enters RECOVERY, NOT immediately RESOLVED
    inc2 = inc_service.update_incident_state(iid, current_sla=0.92, as_of='2026-09-13 17:30:00')
    assert inc2['state'] == 'RECOVERY'
    assert inc2['normal_streak'] == 1

    # Step 3: Second consecutive normal interval at 0.93 -> enters RESOLVED
    inc3 = inc_service.update_incident_state(iid, current_sla=0.93, as_of='2026-09-13 18:00:00')
    assert inc3['state'] == 'RESOLVED'
    assert inc3['normal_streak'] == 2
