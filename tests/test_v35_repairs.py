"""Opsentia — Comprehensive v3.5 Targeted Repairs & Independent Audit Verification Suite
Validates all 5 fixes from Opsentia_v3_5_Independent_Audit_and_Fixes:
- Fix 1 (P0): Zero-lookahead for active incident data in Gemini/chat (interim stats, value-level checks)
- Fix 2 (P0): All Queues multi-horizon KPI reconciliation (34 time buckets, combined staffing ~95.9)
- Fix 3 (P1): Natural-language period resolution ("last month" resolves to August 2026, 97.33% SLA)
- Fix 4 (P1): Calibrate or relabel uncertainty (HEURISTIC_SCENARIO_RANGE, empirical coverage, stratified error)
- Fix 5 (P1): Proactive Gemini intelligence supervisor (opt-in worker, dedupe, cooldown, fake AI client)
Team VYRA · Google Cloud AI Builder Cup 2026.
"""
from __future__ import annotations
import os
import unittest.mock as mock
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from backend.app import app
from backend.analytics import OpsentiaAnalyticsService, compute_weighted_slice, aggregate_queues_by_timestamp
from backend.forecast_service import OpsentiaForecastService
from backend.watchouts import OpsentiaWatchoutsService
from backend.assistant import OpsentiaAssistantService, ChatMessageRequest, resolve_temporal_period
from backend.supervisor import OpsentiaProactiveSupervisor, SupervisionDecision
from backend.agent import OpsentiaAgentService
from backend.coil import CoilEngine
from backend.incidents import IncidentLifecycleService

client = TestClient(app)
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
ops_df = pd.read_csv(os.path.join(DATA_PATH, 'synthetic_operations.csv'), low_memory=False)


# =========================================================================
# FIX 1 (P0): ZERO-LOOKAHEAD FOR ACTIVE INCIDENTS IN CHAT / GEMINI
# =========================================================================

def test_active_incident_interim_statistics_zero_lookahead():
    """Verify active ongoing incident EV-20260913-A at 16:30 reports only interim observed
    statistics (peak 314, min SLA 80.49%) and suppresses post-16:30 outcomes (peak 393, min SLA 45.88%).
    """
    analytics = OpsentiaAnalyticsService(ops_df)
    forecast = OpsentiaForecastService(ops_df)
    watchouts = OpsentiaWatchoutsService(ops_df, analytics, forecast)
    assistant = OpsentiaAssistantService(DATA_PATH, ops_df, analytics, forecast, watchouts)

    as_of = "2026-09-13 16:30:00"
    inc_res = assistant.tool_get_historical_incidents(queue="Queue A", as_of=as_of)

    assert inc_res['count'] > 0
    incs = inc_res['incidents']

    # Find the active incident EV-20260913-A
    active_inc = next((i for i in incs if i['incident_id'] == 'EV-20260913-A'), None)
    assert active_inc is not None, "EV-20260913-A not found in incident list"
    assert active_inc['is_active'] is True
    assert active_inc['outcome_status'] == 'ACTIVE_ONGOING'
    assert active_inc['end_at'] is None, "Future end_at leaked for active incident"

    # Value-level zero leakage assertions:
    # Up to 16:30: peak offered is 314, min SLA is 0.8049 (80.49%)
    assert active_inc['peak_offered_calls'] == 314, f"Leaked post-cutoff peak: {active_inc['peak_offered_calls']}"
    assert active_inc['min_sla'] == 0.8049, f"Leaked post-cutoff min SLA: {active_inc['min_sla']}"

    # Assert completed incidents retain historical facts
    comp_inc = next((i for i in incs if i['incident_id'] == 'EV-20260905-A'), None)
    assert comp_inc is not None
    assert comp_inc['is_active'] is False
    assert comp_inc['end_at'] == "2026-09-05 20:00:00"


def test_chat_response_contains_no_value_level_leakage_for_active_incident():
    """Verify chat API response mentions only interim 314/80.49% and NEVER mentions 393 or 45.88%/45.9%."""
    resp = client.post('/api/assistant/chat', json={
        'message': 'What historical incidents occurred for Queue A?',
        'queue': 'Queue A',
        'as_of': '2026-09-13 16:30:00'
    })
    assert resp.status_code == 200
    data = resp.json()
    answer = data.get('answer', '')

    # Must contain active incident header and observed interim values
    assert 'Active / Ongoing Incidents' in answer or 'ACTIVE_ONGOING' in answer
    assert '314' in answer, "Observed interim peak calls (314) missing from chat answer"
    assert '80.49%' in answer or '80.5%' in answer, "Observed interim min SLA (80.49%) missing from chat answer"

    # Value-level anti-leakage: 393 and 45.9% / 45.88% must NEVER appear
    assert '393' not in answer, "Post-cutoff peak offered (393) leaked in chat response"
    assert '45.9%' not in answer, "Post-cutoff min SLA (45.9%) leaked in chat response"
    assert '45.88%' not in answer, "Post-cutoff min SLA (45.88%) leaked in chat response"


# =========================================================================
# FIX 2 (P0): ALL QUEUES MULTI-HORIZON KPI RECONCILIATION
# =========================================================================

def test_all_queues_intraday_grain_and_staffing_reconciliation():
    """Verify All Queues intraday analytics returns exactly 34 time buckets and 95.9 mean staffing at 16:30."""
    resp = client.get('/api/analytics', params={
        'queue': 'All Queues',
        'grain': 'intraday',
        'as_of': '2026-09-13 16:30:00',
    })
    assert resp.status_code == 200
    data = resp.json()

    summary = data.get('summary', {})
    series = data.get('series', [])

    # Exactly 34 discrete 30-minute intervals elapsed by 16:30
    assert summary.get('intervals_observed') == 34, f"Expected 34 intervals, got {summary.get('intervals_observed')}"
    assert len(series) == 34, f"Expected 34 series items, got {len(series)}"

    # Average combined staffing across 5 queues is ~95.9 agents (not 19.2)
    assert summary.get('avg_available_agents') == 95.9, f"Expected 95.9 staffing, got {summary.get('avg_available_agents')}"

    # Verify no duplicate timestamps in series
    periods = [item['period'] for item in series]
    assert len(periods) == len(set(periods)), "Duplicate periods found in All Queues intraday series"


def test_all_queues_cross_queue_additive_conservation():
    """Verify additive KPIs exactly match sum of 5 queues across every horizon."""
    as_of = '2026-09-13 16:30:00'
    analytics = OpsentiaAnalyticsService(ops_df)

    all_res = analytics.get_analytics(queue='All Queues', grain='intraday', as_of=as_of)
    indiv_queues = ['Queue A', 'Queue B', 'Queue C', 'Retention', 'Support L2']
    q_summaries = [analytics.get_analytics(queue=q, grain='intraday', as_of=as_of)['summary'] for q in indiv_queues]

    sum_offered = sum(s['offered_calls'] for s in q_summaries)
    sum_answered = sum(s['answered_calls'] for s in q_summaries)
    sum_abandoned = sum(s['abandoned_calls'] for s in q_summaries)
    sum_sla_met = sum(s['sla_met_calls'] for s in q_summaries)

    assert all_res['summary']['offered_calls'] == sum_offered
    assert all_res['summary']['answered_calls'] == sum_answered
    assert all_res['summary']['abandoned_calls'] == sum_abandoned
    assert all_res['summary']['sla_met_calls'] == sum_sla_met

    # Call-weighted SLA verification
    expected_sla = round(sum_sla_met / sum_answered, 4)
    assert all_res['summary']['sla'] == expected_sla


# =========================================================================
# FIX 3 (P1): NATURAL-LANGUAGE PERIOD RESOLUTION
# =========================================================================

def test_resolve_temporal_period_semantics():
    """Verify relative natural language date resolution for past and current periods."""
    as_of = "2026-09-13 16:30:00"

    # 'last month' resolves to completed August 2026
    lm = resolve_temporal_period("What happened last month?", as_of)
    assert lm['resolved'] is True
    assert lm['period_type'] == 'PRIOR_MONTH'
    assert lm['grain'] == 'month'
    assert lm['start_date'] == "2026-08-01 00:00:00"
    assert lm['end_date'] == "2026-08-31 23:30:00"
    assert lm['query_as_of'] == "2026-08-31 23:30:00"

    # 'this month' resolves to partial September 2026 MTD
    tm = resolve_temporal_period("Show performance for this month", as_of)
    assert tm['resolved'] is True
    assert tm['period_type'] == 'CURRENT_MONTH'
    assert tm['start_date'] == "2026-09-01 00:00:00"
    assert tm['end_date'] == as_of

    # 'yesterday' resolves to completed 2026-09-12
    yd = resolve_temporal_period("How did we do yesterday?", as_of)
    assert yd['resolved'] is True
    assert yd['period_type'] == 'PRIOR_DAY'
    assert yd['start_date'] == "2026-09-12 00:00:00"
    assert yd['end_date'] == "2026-09-12 23:30:00"


def test_chat_last_month_returns_august_2026_not_september_mtd():
    """Verify 'What happened last month?' returns August 2026 (SLA ~97.33%, 245,840 calls)."""
    resp = client.post('/api/assistant/chat', json={
        'message': 'What happened last month?',
        'queue': 'Queue A',
        'as_of': '2026-09-13 16:30:00'
    })
    assert resp.status_code == 200
    answer = resp.json().get('answer', '')

    # Must specify August 2026
    assert 'August 2026' in answer, f"Expected August 2026 in answer, got: {answer[:200]}"
    assert '97.33%' in answer or '97.3%' in answer, "Expected August 2026 SLA 97.33% in answer"
    assert '245,840' in answer, "Expected August 2026 volume 245,840 in answer"

    # Must NOT report September MTD 96.37%
    assert '96.37%' not in answer, "Erroneously returned September MTD SLA instead of August"


# =========================================================================
# FIX 4 (P1): UNCERTAINTY RELABELING & STRATIFIED ERROR REPORTING
# =========================================================================

def test_forecast_uncertainty_relabeling_heuristic_scenario_range():
    """Verify forecast uncertainty is labeled HEURISTIC_SCENARIO_RANGE and limitations disclosed."""
    resp = client.get('/api/forecasts/full-day', params={'queue': 'Queue A', 'as_of': '2026-09-13 16:30:00'})
    assert resp.status_code == 200
    data = resp.json()

    p = data['projected_full_day']
    assert p['range_type'] == 'HEURISTIC_SCENARIO_RANGE'
    assert p['sla_range_type'] == 'HEURISTIC_SCENARIO_RANGE'

    # Check limitations disclose heuristic scenario sensitivity bounds
    lims = " ".join(data.get('limitations', []))
    assert 'HEURISTIC_SCENARIO_RANGE' in lims
    assert 'not mathematically calibrated statistical confidence intervals' in lims
    assert '2026-09-12' in lims, "Missing disclosure of demonstrated out-of-range benchmark day"


def test_forecast_backtest_reports_empirical_coverage_and_sample_sizes():
    """Verify backtest reports heuristic empirical coverage and separate normal/incident sample sizes."""
    fc_service = OpsentiaForecastService(ops_df)
    bt = fc_service.backtest_full_day(queue='Queue A', as_of='2026-09-13 16:30:00', eval_days=7)

    assert bt['status'] == 'OK'
    assert bt['range_type'] == 'HEURISTIC_SCENARIO_RANGE'
    assert bt['calibration_status'] == 'UNCALIBRATED_HEURISTIC_BOUNDS'
    assert 'heuristic_range_coverage_pct' in bt
    assert 'normal_days_sample_size' in bt
    assert 'incident_days_sample_size' in bt
    assert bt['normal_days_sample_size'] + bt['incident_days_sample_size'] == bt['evaluation_window_days']


# =========================================================================
# FIX 5 (P1): PROACTIVE GEMINI INTELLIGENCE SUPERVISOR
# =========================================================================

def test_supervisor_status_endpoint():
    """Verify supervisor health and safety contract (human approval mandatory)."""
    resp = client.get('/api/coil/supervisor/status')
    assert resp.status_code == 200
    data = resp.json()
    assert data['safety_contract'] == 'HUMAN_APPROVAL_MANDATORY'
    assert data['autonomous_execution_allowed'] is False


def test_supervisor_opt_in_and_insignificant_interval_skipping():
    """Verify supervisor does not invoke AI on normal/insignificant intervals."""
    coil = CoilEngine(ops_df)
    inc_svc = IncidentLifecycleService(os.path.join(DATA_PATH))
    agent = OpsentiaAgentService(DATA_PATH, ops_df)
    supervisor = OpsentiaProactiveSupervisor(ops_df, agent, coil, inc_svc, enabled=False)

    # 1. Disabled supervisor skips evaluation
    res_disabled = supervisor.evaluate_tick(queue='Queue A', as_of='2026-09-13 10:00:00', force_enable=False)
    assert res_disabled.supervisor_enabled is False
    assert res_disabled.reason == 'SKIPPED_SUPERVISOR_DISABLED'
    assert res_disabled.triggered is False

    # 2. Enabled supervisor on normal morning interval (no breach, no active incident)
    res_normal = supervisor.evaluate_tick(queue='Queue A', as_of='2026-09-13 10:00:00', force_enable=True)
    assert res_normal.supervisor_enabled is True
    assert res_normal.triggered is False
    assert res_normal.reason == 'INSIGNIFICANT_INTERVAL'


def test_supervisor_triggers_on_state_change_with_fake_ai_client():
    """Verify supervisor triggers AI investigation on critical state change using injected fake AI client."""
    coil = CoilEngine(ops_df)
    inc_svc = IncidentLifecycleService(os.path.join(DATA_PATH))
    agent = OpsentiaAgentService(DATA_PATH, ops_df)
    supervisor = OpsentiaProactiveSupervisor(ops_df, agent, coil, inc_svc, enabled=True)

    # Injected fake AI client
    fake_ai_called = []
    class FakeGeminiClient:
        def __init__(self):
            self.models = self
        def generate_content(self, model, contents, config):
            fake_ai_called.append({'model': model, 'contents': contents})
            class FakeResp:
                text = '{"executive_summary":"Injected supervisor AI investigation summary","hypotheses":[{"label":"Spike","status":"SUPPORTED"}],"forecast":{"projected_sla":0.82},"recommendation":{"action":"Add staff","rationale":"Mitigate"}}'
            return FakeResp()

    fake_client = FakeGeminiClient()

    # Trigger at 16:30 (Queue A is in active incident / critical stress)
    decision = supervisor.evaluate_tick(
        queue='Queue A',
        as_of='2026-09-13 16:30:00',
        incident_id='EV-2026-0913-01',
        force_enable=True,
        custom_ai_client=fake_client,
    )

    assert decision.triggered is True
    assert decision.severity in ('HIGH', 'CRITICAL')
    assert decision.trace_id is not None
    assert decision.autonomous_changes_made is False
    assert decision.human_approval_required is True
    assert len(fake_ai_called) == 1, "Injected AI client was not called on critical state change"


def test_supervisor_deduplication_and_cooldown():
    """Verify deduplication prevents duplicate investigations for same (incident_id, severity, timestamp)."""
    coil = CoilEngine(ops_df)
    inc_svc = IncidentLifecycleService(os.path.join(DATA_PATH))
    agent = OpsentiaAgentService(DATA_PATH, ops_df)
    supervisor = OpsentiaProactiveSupervisor(ops_df, agent, coil, inc_svc, enabled=True, cooldown_minutes=60)

    # Seed incident in inc_svc with HIGH severity
    inc_svc.incidents['EV-2026-0913-01'] = {'incident_id': 'EV-2026-0913-01', 'severity': 'HIGH', 'state': 'HIGH'}

    # First call triggers
    d1 = supervisor.evaluate_tick(queue='Queue A', as_of='2026-09-13 16:30:00', incident_id='EV-2026-0913-01', force_enable=True)
    assert d1.triggered is True

    # Immediate second call at same timestamp returns DEDUPLICATED
    d2 = supervisor.evaluate_tick(queue='Queue A', as_of='2026-09-13 16:30:00', incident_id='EV-2026-0913-01', force_enable=True)
    assert d2.triggered is False
    assert d2.reason == 'DEDUPLICATED'

    # Advance clock to next interval (17:00, within 60 min cooldown) with same severity
    d3 = supervisor.evaluate_tick(queue='Queue A', as_of='2026-09-13 17:00:00', incident_id='EV-2026-0913-01', force_enable=True)
    assert d3.triggered is False
    assert d3.reason == 'COOLDOWN_ACTIVE'


def test_replay_advance_endpoint_with_opt_in_supervisor():
    """Verify POST /api/coil/replay/advance optionally triggers proactive supervision on interval tick."""
    resp = client.post('/api/coil/replay/advance', json={
        'current_as_of': '2026-09-13 16:00:00',
        'minutes': 30,
        'enable_proactive_supervisor': True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['new_as_of'] == '2026-09-13 16:30:00'
    assert 'supervision' in data
    assert data['supervision'] is not None
    assert data['supervision']['supervisor_enabled'] is True
