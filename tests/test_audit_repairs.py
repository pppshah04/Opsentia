"""Acceptance Test Suite for Opsentia v3 Audit Repairs.
Directly validates all 10 acceptance criteria specified in ANTIGRAVITY_TARGETED_FIXES.md.
"""
import os
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import app, incident_service
from backend.agent import OpsentiaAgentService
from backend.coil import CoilEngine
from backend.simulation import DecisionSimulationService

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
ops_df = pd.read_csv(DATA / 'synthetic_operations.csv', low_memory=False)
client = TestClient(app)


def test_simulation_declares_uncalibrated_baseline():
    """Acceptance Test 1: Simulation truth:
    Show observed 80.49% vs modeled 14.95% baseline truthfully;
    No false claim of validated +72.29pp operational uplift.
    """
    sim = DecisionSimulationService(ops_df)
    as_of = '2026-09-13 16:30:00'
    res = sim.simulate_scenario(
        queue='Queue A',
        as_of=as_of,
        scenario_type='add_temporary_agents',
        agents_to_add=8,
        duration_hours=4.0
    )

    # 1. Truthful decomposition
    assert res['observed_sla_pct'] == 80.49, f"Observed SLA must be 80.49%, got {res['observed_sla_pct']}"
    assert res['modeled_no_action_sla_pct'] == 14.95, f"Modeled baseline must be 14.95%, got {res['modeled_no_action_sla_pct']}"
    assert res['modeled_action_sla_pct'] == 87.24, f"Modeled action SLA must be 87.24%, got {res['modeled_action_sla_pct']}"

    # 2. Calibration error and uncalibrated classification
    assert res['calibration_error'] == 65.54, f"Calibration discrepancy must be 65.54pp, got {res['calibration_error']}"
    assert res['is_calibrated'] is False
    assert res['prediction_status'] == 'UNVALIDATED_STEADY_STATE_PROXY'
    assert res['calibration_warning'] is not None
    assert 'diverges from observed SLA' in res['calibration_warning']
    assert 'must NOT be claimed as validated operational uplift' in res['calibration_warning']

    # 3. Model-relative delta vs observed difference
    assert res['modeled_relative_delta_pp'] == 72.29
    assert res['difference_from_observed_pp'] == 6.75


def test_invalid_scenario_returns_error():
    """Acceptance Test 2: Invalid scenario ID returns error; no silent Queue A +8 default."""
    agent = OpsentiaAgentService(DATA, ops_df)
    res = agent.tool_simulate_intervention('INVALID-SCENARIO-UNKNOWN-999', '2026-09-13 16:30:00')

    assert res.get('status') == 'ERROR'
    assert res.get('error') == 'UNKNOWN_SCENARIO'
    assert 'not found in catalog' in res.get('message', '')


def test_scenario_target_queue_respected():
    """Acceptance Test 3: Scenario target queue is respected; Queue B scenario cannot run against Queue A."""
    agent = OpsentiaAgentService(DATA, ops_df)
    # EV-20260420-B-S1 targets Queue B
    res = agent.tool_simulate_intervention(
        scenario_id='EV-20260420-B-S1',
        as_of='2026-04-20 15:00:00',
        expected_queue='Queue A'
    )

    assert res.get('status') == 'ERROR'
    assert res.get('error') == 'QUEUE_MISMATCH'
    assert 'targets Queue B, cannot run against Queue A' in res.get('message', '')


def test_unauthenticated_approval_denied():
    """Acceptance Test 4: Approvals: any request-supplied actor/role string cannot authorize an action
    without valid demo authorization credentials.
    """
    res = client.post('/api/decisions/ACT-0001/approve', json={
        'actor': 'Arbitrary Attacker',
        'role': 'Operations Director',
        'as_of': '2026-09-13 16:35:00',
        'rationale': 'Unauthorized attempt'
    })
    assert res.status_code == 401
    assert 'UNAUTHENTICATED_APPROVAL' in res.json().get('detail', '')


def test_approval_wrong_action_id_denied():
    """Acceptance Test 5: UI approval uses selected stored action; HTTP 409 is conflict, not success."""
    # Draft a new pending action on app's incident_service
    action = incident_service.create_action(
        incident_id='EV-2026-0913-01',
        action_type='add_temporary_agents',
        owner_role='Real-Time Operations Lead',
        rationale='Testing state transitions',
        as_of='2026-09-13 16:30:00'
    )
    action_id = action['action_id']

    import backend.app as app_module
    app_module.OPSENTIA_OPERATOR_TOKEN = "test-eval-operator-secret"

    s_res = client.get('/api/auth/demo-session', headers={'X-Operator-Token': app_module.OPSENTIA_OPERATOR_TOKEN})
    assert s_res.status_code == 200
    token = s_res.json()['session_token']

    # 1. Non-existent action ID returns 404
    wrong_res = client.post(
        '/api/decisions/ACT-NONEXISTENT-9999/approve',
        headers={'Authorization': f'Bearer {token}'},
        json={'actor': 'Director', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
    )
    assert wrong_res.status_code == 404

    # 2. First approval succeeds with 200
    first_res = client.post(
        f'/api/decisions/{action_id}/approve',
        headers={'Authorization': f'Bearer {token}'},
        json={'actor': 'Director', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
    )
    assert first_res.status_code == 200
    assert first_res.json()['approval_status'] == 'APPROVED'
    assert first_res.json()['approval_mode'] == 'SIMULATED_APPROVAL'

    # 3. Second approval attempts duplicate transition on already-approved action -> HTTP 409 Conflict
    second_res = client.post(
        f'/api/decisions/{action_id}/approve',
        headers={'Authorization': f'Bearer {token}'},
        json={'actor': 'Director', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
    )
    assert second_res.status_code == 409, "Duplicate approval must return HTTP 409 Conflict, not 200"


def test_asof_filters_policies_memory_historical_matches():
    """Acceptance Test 6: Zero future leakage: as_of filters policies, decision memory,
    and historical incident matches.
    """
    agent = OpsentiaAgentService(DATA, ops_df)

    # 1. Policies: DOC-006 is effective only 2026-08-01 to 2026-08-17.
    # At 2026-09-13 (after expiration), DOC-006 must NOT be returned.
    policies_sept = agent.tool_search_enterprise_policy('campaign marketing', as_of='2026-09-13 16:30:00')
    doc_ids_sept = [d['document_id'] for d in policies_sept.get('documents', [])]
    assert 'DOC-006' not in doc_ids_sept, "Expired policy DOC-006 should not be active in September"

    # At 2026-08-10 (during window), DOC-006 IS returned.
    policies_aug = agent.tool_search_enterprise_policy('campaign marketing', as_of='2026-08-10 14:00:00')
    doc_ids_aug = [d['document_id'] for d in policies_aug.get('documents', [])]
    assert 'DOC-006' in doc_ids_aug, "Active policy DOC-006 should be returned during effective window"

    # 2. Historical matches: as of 2026-04-01, future incidents (April 8, April 20, May, etc.) must not appear
    matches = agent.tool_get_similar_incidents('EV-20260408-L2', limit=10, as_of='2026-04-01 00:00:00')
    for m in matches.get('matches', []):
        if m.get('date') != 'Historical':
            assert m['date'] < '2026-04-01', f"Future match {m} leaked before as_of date"

    # 3. Decision memory: actions created after as_of must not appear
    memory = agent.tool_get_incident_decision_memory('EV-2026-0913-01', as_of='2026-04-01 00:00:00')
    for act in memory.get('historical_actions', []):
        if act.get('created_at'):
            assert act['created_at'] < '2026-04-01', f"Future action {act} leaked before as_of"


def test_notifications_counts_reconcile():
    """Acceptance Test 7: Notification counts reconcile with ledger;
    Real delivery is never asserted for simulation.
    """
    res = client.get('/api/notifications')
    assert res.status_code == 200
    data = res.json()
    summary = data['summary']
    events = data['events']

    # Total events matches ledger length
    assert summary['TOTAL_EVENTS'] == len(events)
    assert summary['TOTAL_EVENTS'] == summary['FIXTURE_EVENTS'] + summary['RUNTIME_SIMULATED_EVENTS']

    # Delivery truth assertions
    assert summary['REAL_DELIVERY_ASSERTED'] is False
    assert summary['DELIVERY_MODE'] == 'SIMULATED_DISPATCH_ONLY'
    assert 'NOT asserted in simulation mode' in data.get('governance_note', '')


@pytest.mark.skipif(
    not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
    reason="Integration test requires GEMINI_API_KEY (truthfully skipped when unconfigured)"
)
def test_real_gemini_model_selected_two_tools():
    """Acceptance Test 8: Live Gemini agent selects at least 2 distinct read-only tools at runtime.
    Captures model ID, function arguments, execution status, and grounding.
    """
    agent = OpsentiaAgentService(DATA, ops_df)
    res = agent.investigate(
        incident_id='EV-2026-0913-01',
        queue='Queue A',
        as_of='2026-09-13 16:30:00',
        force_fallback=False
    )
    assert res.ai_mode == 'GEMINI_LIVE'
    assert res.investigation_status in ('LIVE_VERIFIED', 'MODEL_SELECTED_TOOL_CALLS_VERIFIED')
    assert len(res.tool_calls) >= 2
    distinct_tools = {tc['name'] for tc in res.tool_calls}
    assert len(distinct_tools) >= 2


def test_replay_forecast_error():
    """Acceptance Test 9: Replay timing:
    At 16:30, COIL predicts breach at 17:30 (time-to-breach 60m).
    Actual observed breach is at 17:00 (SLA 70.50% < 75%).
    Advance warning lead time is 30m; timing error is 30m. Not conflated.
    """
    coil = CoilEngine(ops_df)
    res = coil.evaluate_replay_forecast_accuracy('Queue A', '2026-09-13 16:30:00')

    assert res['predicted_breach'] is True
    assert res['predicted_breach_timestamp'] == '2026-09-13 17:30:00'
    assert res['predicted_time_to_breach_minutes'] == 60

    assert res['observed_breach_timestamp'] == '2026-09-13 17:00:00'
    assert res['advance_warning_lead_minutes'] == 30
    assert res['timing_error_minutes'] == 30

    assert 'Warning lead time and timing error are measured and reported separately' in res['calibration_note']


def test_cloud_run_health_and_safe_writes():
    """Acceptance Test 10: Public endpoints are safe; mutating APIs are restricted; no secrets leaked."""
    # 1. Health endpoint
    h = client.get('/api/health')
    assert h.status_code == 200
    assert h.json()['ok'] is True
    assert h.json()['product'] == 'Opsentia'

    # 2. Data coverage endpoint
    dc = client.get('/api/data-coverage')
    assert dc.status_code == 200
    assert len(dc.json()['queues']) == 5

    # 3. Snapshot endpoint
    snap = client.get('/api/coil/snapshot')
    assert snap.status_code == 200

    # 4. No secrets in responses
    for resp in (h, dc, snap):
        body_text = resp.text
        assert 'AIza' not in body_text
        assert 'sk-' not in body_text
        assert 'PRIVATE KEY' not in body_text

    # 5. Mutating approval rejected without auth
    mut = client.post('/api/decisions/ACT-0001/approve', json={})
    assert mut.status_code == 401


def test_demo_session_auth_and_tamper_defense():
    """Acceptance Test 11: Dynamic demo session authentication and role tamper defense.
    Ensures browser does not need hardcoded tokens; server binds identity to session principal.
    """
    import backend.app as app_module
    app_module.OPSENTIA_OPERATOR_TOKEN = "test-eval-operator-secret"

    # 1. Fetch dynamic authenticated session token using operator secret
    s_res = client.get('/api/auth/demo-session', headers={'X-Operator-Token': app_module.OPSENTIA_OPERATOR_TOKEN})
    assert s_res.status_code == 200
    token = s_res.json()['session_token']
    assert token.startswith('demo-session-')

    # 2. Rejection without auth
    no_auth = client.post('/api/decisions/ACT-0002/approve', json={'actor': 'Hacker', 'role': 'Admin'})
    assert no_auth.status_code == 401
    assert 'UNAUTHENTICATED_APPROVAL' in no_auth.json()['detail']
    # Ensure error detail does not leak hardcoded secrets
    assert 'ops-lead-2026' not in no_auth.json()['detail']

    # 3. Acceptance with Bearer operator session token; verifies role tamper defense
    auth_res = client.post(
        '/api/decisions/ACT-0002/approve',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'actor': 'Spoofed Client Identity',
            'role': 'Arbitrary Client Role',
            'as_of': '2026-09-13 16:35:00',
            'rationale': 'Approved mitigation via verified demo session',
        }
    )
    # Either 200 OK or 409 Conflict (if already approved in prior runs)
    assert auth_res.status_code in (200, 409)
    if auth_res.status_code == 200:
        act = auth_res.json()['action']
        assert 'operator' in act['approved_by'] or 'session-principal' in act['approved_by']
        assert act['owner_role'] == 'Operations Director (Simulated)'



def test_multiscenario_decision_simulation_comparison():
    """Acceptance Test 12: Multi-scenario decision comparison.
    Compares no-action, +5 agents, +8 agents, and Queue B transfer with donor floor protection.
    Verifies mathematical monotonicity and truthful unvalidated steady-state labeling.
    """
    # 1. No action
    s0 = client.post('/api/simulations', json={
        'queue': 'Queue A',
        'as_of': '2026-09-13 16:30:00',
        'scenario_type': 'no_action',
        'agents_to_add': 0,
        'agents_to_transfer': 0,
    }).json()

    # 2. Add 5 agents
    s5 = client.post('/api/simulations', json={
        'queue': 'Queue A',
        'as_of': '2026-09-13 16:30:00',
        'scenario_type': 'add_temporary_agents',
        'agents_to_add': 5,
        'agents_to_transfer': 0,
        'duration_hours': 4.0,
        'hourly_rate_usd': 45.0,
    }).json()

    # 3. Add 8 agents
    s8 = client.post('/api/simulations', json={
        'queue': 'Queue A',
        'as_of': '2026-09-13 16:30:00',
        'scenario_type': 'add_temporary_agents',
        'agents_to_add': 8,
        'agents_to_transfer': 0,
        'duration_hours': 4.0,
        'hourly_rate_usd': 45.0,
    }).json()

    # 4. Transfer 4 agents from Queue B
    s_tr = client.post('/api/simulations', json={
        'queue': 'Queue A',
        'as_of': '2026-09-13 16:30:00',
        'scenario_type': 'transfer_agents',
        'agents_to_add': 0,
        'agents_to_transfer': 4,
        'donor_queue': 'Queue B',
        'donor_sla_floor': 0.85,
    }).json()

    # Verification: Distinct costs
    assert s0['estimated_cost_usd'] == 0.0
    assert s5['estimated_cost_usd'] == 5 * 45 * 4
    assert s8['estimated_cost_usd'] == 8 * 45 * 4

    # Verification: Capacity monotonicity SLA(+8) >= SLA(+5) >= SLA(no-action)
    assert s8['projected_sla'] >= s5['projected_sla']
    assert s5['projected_sla'] >= s0['projected_sla']

    # Verification: Donor impact evaluated on transfer
    assert s_tr['donor_impact'] is not None
    assert s_tr['donor_impact']['donor_queue'] == 'Queue B'
    assert s_tr['agents_transferred'] == 4
    assert s_tr['donor_impact']['donor_agents_before'] - s_tr['donor_impact']['donor_agents_after'] == 4

    # Verification: Truthful disclosure and zero fake uplift
    for s in (s0, s5, s8, s_tr):
        assert s['prediction_status'] == 'UNVALIDATED_STEADY_STATE_PROXY'
        assert s['model_name'] == 'ERLANG_C_CAPACITY_PROXY'
        assert s['sla_uplift_claimed'] is False


def test_session_expiry_and_static_token_rejection():
    """Acceptance Test 13: Enforce session expiry, static token deletion, and unauthenticated write defense."""
    import time
    from backend.app import ACTIVE_DEMO_SESSIONS

    # 1. Static demo token 'ops-lead-2026' is rejected (no longer accepted)
    static_res = client.post(
        '/api/decisions/ACT-0001/approve',
        headers={'X-Demo-Approver': 'ops-lead-2026'},
        json={'actor': 'Director', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
    )
    assert static_res.status_code == 401
    assert 'INVALID_CREDENTIALS' in static_res.json()['detail'] or 'UNAUTHENTICATED' in static_res.json()['detail']

    # 2. Expired session token is rejected
    expired_token = "demo-session-expired-test"
    ACTIVE_DEMO_SESSIONS[expired_token] = {
        'principal': 'session-principal:expired',
        'role': 'Operations Director (Simulated)',
        'can_mutate': True,
        'created_at': time.time() - 7200,
        'expires_at': time.time() - 3600,  # Expired 1 hour ago
    }
    exp_res = client.post(
        '/api/decisions/ACT-0001/approve',
        headers={'Authorization': f'Bearer {expired_token}'},
        json={'actor': 'Director', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
    )
    assert exp_res.status_code == 401
    assert 'SESSION_EXPIRED' in exp_res.json()['detail']


def test_public_demo_read_only_mode_blocks_mutations():
    """Acceptance Test 14 (P0-01 Adversarial Security Integration Test):
    Verify that unauthenticated/anonymous callers cannot elevate sessions or execute mutations,
    while authorized operators with non-empty secrets succeed.
    """
    import backend.app as app_module

    # Save original settings
    orig_ro = app_module.PUBLIC_DEMO_READ_ONLY
    orig_op = app_module.OPSENTIA_OPERATOR_TOKEN

    try:
        app_module.PUBLIC_DEMO_READ_ONLY = True
        app_module.OPSENTIA_OPERATOR_TOKEN = "verified-eval-secret-2026"

        # 1. Anonymous visitor calls GET /api/auth/demo-session without credentials
        s_res = client.get('/api/auth/demo-session')
        assert s_res.status_code == 200
        data = s_res.json()
        assert data['can_mutate'] is False
        assert data['role'] == 'Operations Viewer (Read-Only)'
        assert data['mode'] == 'PUBLIC_DEMO_READ_ONLY'
        assert data['mutation_policy'] == 'MUTATIONS_DISABLED_READ_ONLY'
        ro_token = data['session_token']

        # Draft a valid pending action
        action = incident_service.create_action(
            incident_id='EV-2026-0913-01',
            action_type='add_temporary_agents',
            owner_role='Real-Time Operations Lead',
            rationale='Adversarial penetration test',
            as_of='2026-09-13 16:30:00'
        )
        action_id = action['action_id']

        # 2. Adversarial attempt: anonymous session attempts POST /api/decisions/{id}/approve -> HTTP 403 Forbidden
        mut_res = client.post(
            f'/api/decisions/{action_id}/approve',
            headers={'Authorization': f'Bearer {ro_token}'},
            json={'actor': 'Malicious Visitor', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
        )
        assert mut_res.status_code == 403, "Anonymous session must be blocked from action approval with HTTP 403"
        assert 'PUBLIC_DEMO_READ_ONLY' in mut_res.json()['detail']

        # 3. Adversarial attempt: anonymous session attempts POST /api/decisions/{id}/reject -> HTTP 403 Forbidden
        rej_res = client.post(
            f'/api/decisions/{action_id}/reject',
            headers={'Authorization': f'Bearer {ro_token}'},
            json={'actor': 'Malicious Visitor', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00', 'rationale': 'Reject attempt'}
        )
        assert rej_res.status_code == 403, "Anonymous session must be blocked from action rejection with HTTP 403"

        # 4. Adversarial attempt: anonymous session attempts incident acknowledge -> HTTP 403 Forbidden
        ack_res = client.post(
            '/api/incident/EV-2026-0913-01/acknowledge',
            headers={'Authorization': f'Bearer {ro_token}'},
            json={'actor': 'Malicious Visitor', 'as_of': '2026-09-13 16:35:00'}
        )
        assert ack_res.status_code == 403, "Anonymous session must be blocked from incident acknowledge with HTTP 403"

        # 5. Direct call with no token -> HTTP 401 Unauthorized
        no_tok_res = client.post(
            f'/api/decisions/{action_id}/approve',
            json={'actor': 'No Token Attacker', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
        )
        assert no_tok_res.status_code == 401

        # 6. Direct call with forged/unknown token -> HTTP 401 Unauthorized
        fake_tok_res = client.post(
            f'/api/decisions/{action_id}/approve',
            headers={'Authorization': 'Bearer demo-session-fake-forged-1234'},
            json={'actor': 'Fake Token Attacker', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
        )
        assert fake_tok_res.status_code == 401

        # 7. Authorized Operator provides valid secret to mint an operator session -> succeeds
        op_sess_res = client.get(
            '/api/auth/demo-session',
            headers={'X-Operator-Token': app_module.OPSENTIA_OPERATOR_TOKEN}
        )
        assert op_sess_res.status_code == 200
        op_data = op_sess_res.json()
        assert op_data['can_mutate'] is True
        assert op_data['role'] == 'Operations Director (Authenticated)'
        assert op_data['mode'] == 'AUTHENTICATED_OPERATOR_SESSION'
        op_session_token = op_data['session_token']

        # 8. Operator approves valid pending action using dynamic operator session token -> HTTP 200 OK
        valid_approve_res = client.post(
            f'/api/decisions/{action_id}/approve',
            headers={'Authorization': f'Bearer {op_session_token}'},
            json={'actor': 'Legitimate Director', 'role': 'Operations Director', 'as_of': '2026-09-13 16:35:00'}
        )
        assert valid_approve_res.status_code == 200
        assert valid_approve_res.json()['approval_status'] == 'APPROVED'
        assert valid_approve_res.json()['approval_mode'] == 'SIMULATED_APPROVAL'

    finally:
        app_module.PUBLIC_DEMO_READ_ONLY = orig_ro
        app_module.OPSENTIA_OPERATOR_TOKEN = orig_op

