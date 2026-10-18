"""Test Suite for RG-10, RG-11, and RG-12: Incident Lifecycle, Human Approval Workflow,
Notification Deduplication & Cooldown, and Action Audit Records.
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.incidents import IncidentLifecycleService

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
client = TestClient(app)


def test_human_approval_state_machine_and_audit():
    """RG-10: Action state machine enforces valid transitions and records human approver/role."""
    svc = IncidentLifecycleService(DATA)
    as_of = '2026-09-13 16:30:00'

    # Step 1: Create action in PROPOSED / PENDING_APPROVAL state
    action = svc.create_action(
        incident_id='EV-2026-0913-01',
        action_type='add_temporary_agents',
        owner_role='Real-Time Operations Lead',
        rationale='Capacity deficit mitigation',
        as_of=as_of
    )
    act_id = action['action_id']
    assert action['approval_status'] == 'PENDING_APPROVAL'
    assert action['execution_status'] == 'PROPOSED'

    # Step 2: Valid approval by authorized role
    approved = svc.approve_action(
        action_id=act_id,
        actor='Sarah Jenkins',
        role='Operations Director',
        as_of='2026-09-13 16:35:00',
        rationale='Approved after reviewing Decision Lab simulation'
    )
    assert approved['approval_status'] == 'APPROVED'
    assert approved['execution_status'] == 'SIMULATED_IN_PROGRESS'
    assert 'Sarah Jenkins (Operations Director)' in approved['approved_by']
    assert approved['approved_at'] == '2026-09-13 16:35:00'

    # Step 3: Reject illegal duplicate transition on already approved action
    re_approved = svc.approve_action(
        action_id=act_id,
        actor='John Doe',
        role='Manager',
        as_of='2026-09-13 16:40:00'
    )
    assert 'error' in re_approved
    assert re_approved['status_code'] == 409


def test_notification_deduplication_and_cooldown():
    """RG-11: Escalation routing suppresses duplicate notifications within the cooldown window."""
    svc = IncidentLifecycleService(DATA)
    iid = 'EV-2026-0913-01'
    as_of_1 = '2026-09-13 16:30:00'

    # Dispatch 1: HIGH severity alert at 16:30 -> dispatches simulated sent
    batch1 = svc.route_notifications(iid, severity='HIGH', as_of=as_of_1)
    assert len(batch1) > 0
    assert any(e['delivery_status'] == 'SIMULATED_SENT' for e in batch1)

    # Dispatch 2: Same incident, same severity 10 minutes later (16:40, within 60m cooldown)
    as_of_2 = '2026-09-13 16:40:00'
    batch2 = svc.route_notifications(iid, severity='HIGH', as_of=as_of_2)
    assert len(batch2) > 0
    # Must be suppressed due to active cooldown
    assert all(e['delivery_status'] == 'SIMULATED_SUPPRESSED' for e in batch2)

    # Check reconciled ledger counts
    ledger = svc.get_incident_notifications(incident_id=iid)
    sum_data = ledger['summary']
    assert sum_data['SIMULATED_SENT'] > 0
    assert sum_data['SIMULATED_SUPPRESSED'] > 0
    assert sum_data['TOTAL_EVENTS'] == sum_data['SIMULATED_SENT'] + sum_data['SIMULATED_SUPPRESSED'] + sum_data['SIMULATED_FAILED'] + sum_data['ACKNOWLEDGED']


def test_action_tracking_api():
    """RG-12: Full API flow: list actions, approve action, view action ledger."""
    import backend.app as app_module
    app_module.OPSENTIA_OPERATOR_TOKEN = "test-eval-operator-secret"

    # List actions
    list_res = client.get('/api/actions')
    assert list_res.status_code == 200
    acts = list_res.json()['actions']
    assert len(acts) > 0

    # Obtain authenticated operator session
    s_res = client.get('/api/auth/demo-session', headers={'X-Operator-Token': app_module.OPSENTIA_OPERATOR_TOKEN})
    assert s_res.status_code == 200
    assert s_res.json()['can_mutate'] is True
    token = s_res.json()['session_token']

    # Pick an existing action or approve via API
    target_id = acts[0]['action_id']
    app_res = client.post(
        f'/api/decisions/{target_id}/approve',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'actor': 'Director Alice',
            'role': 'Operations Director',
            'as_of': '2026-09-13 16:35:00',
            'rationale': 'Approved via test suite'
        }
    )
    # Either successfully approved (200) or already approved conflict (409)
    assert app_res.status_code in (200, 409)


def test_incident_acknowledge_api():
    """RG-11 & RG-12: Human operator acknowledges incident with authenticated authorization."""
    import backend.app as app_module
    app_module.OPSENTIA_OPERATOR_TOKEN = "test-eval-operator-secret"

    # 1. Unauthenticated attempt fails with 401
    unauth = client.post('/api/incident/EV-2026-0913-01/acknowledge', json={
        'actor': 'Lead Operator John',
        'as_of': '2026-09-13 16:32:00'
    })
    assert unauth.status_code == 401

    # 2. Anonymous session without operator elevation fails with 403
    anon_sess = client.get('/api/auth/demo-session')
    assert anon_sess.status_code == 200
    assert anon_sess.json()['can_mutate'] is False
    anon_ack = client.post(
        '/api/incident/EV-2026-0913-01/acknowledge',
        headers={'Authorization': f"Bearer {anon_sess.json()['session_token']}"},
        json={'actor': 'Lead Operator John', 'as_of': '2026-09-13 16:32:00'}
    )
    assert anon_ack.status_code == 403

    # 3. Authenticated operator session succeeds
    s_res = client.get('/api/auth/demo-session', headers={'X-Operator-Token': app_module.OPSENTIA_OPERATOR_TOKEN})
    assert s_res.status_code == 200
    token = s_res.json()['session_token']

    ack_res = client.post(
        '/api/incident/EV-2026-0913-01/acknowledge',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'actor': 'Lead Operator John',
            'as_of': '2026-09-13 16:32:00'
        }
    )
    assert ack_res.status_code == 200
    data = ack_res.json()
    assert 'operator' in data['acknowledged_by'] or 'session-principal' in data['acknowledged_by']
    assert data['acknowledged_at'] == '2026-09-13 16:32:00'

