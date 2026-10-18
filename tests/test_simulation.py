"""Test Suite for RG-09: Decision Lab Counterfactual Simulation,
Erlang Capacity Proxy, Monotonicity Invariants, and Donor Queue Protection.
"""
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.simulation import DecisionSimulationService, erlang_c_sla_proxy

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
ops_df = pd.read_csv(DATA / 'synthetic_operations.csv', low_memory=False)
client = TestClient(app)


def test_erlang_proxy_monotonicity():
    """RG-09: Under fixed demand, adding available agents strictly cannot worsen expected SLA."""
    offered = 200.0
    aht = 300.0

    sla_20 = erlang_c_sla_proxy(offered, aht, agents=20)
    sla_25 = erlang_c_sla_proxy(offered, aht, agents=25)
    sla_30 = erlang_c_sla_proxy(offered, aht, agents=30)
    sla_40 = erlang_c_sla_proxy(offered, aht, agents=40)

    assert sla_20 <= sla_25 <= sla_30 <= sla_40, (
        f"Monotonicity violated: 20 agents -> {sla_20}, 25 -> {sla_25}, 30 -> {sla_30}, 40 -> {sla_40}"
    )
    assert 0.0 <= sla_20 <= 1.0
    assert 0.0 <= sla_40 <= 1.0


def test_decision_simulation_no_action_baseline():
    """RG-09: Baseline scenario with 0 added agents produces 0 cost and no donor impact."""
    sim = DecisionSimulationService(ops_df)
    as_of = '2026-09-13 16:30:00'
    res = sim.simulate_scenario(
        queue='Queue A',
        as_of=as_of,
        scenario_type='no_action',
        agents_to_add=0,
        agents_to_transfer=0,
    )

    assert res['agents_added'] == 0
    assert res['agents_transferred'] == 0
    assert res['estimated_cost_usd'] == 0.0
    assert res['sla_uplift_pp'] == 0.0
    assert res['donor_impact'] is None


def test_decision_simulation_donor_queue_guardrail():
    """RG-09: Transferring agents from donor Queue B degrades donor queue.
    If donor projected SLA breaches 0.85 floor, constraint violation is flagged.
    """
    sim = DecisionSimulationService(ops_df)
    as_of = '2026-09-13 16:30:00'

    # Safe minor transfer of 2 agents
    safe_res = sim.simulate_scenario(
        queue='Queue A',
        as_of=as_of,
        scenario_type='transfer_agents',
        agents_to_transfer=2,
        donor_queue='Queue B',
        donor_sla_floor=0.85,
    )
    assert safe_res['donor_impact'] is not None
    assert safe_res['donor_impact']['donor_agents_after'] == safe_res['donor_impact']['donor_agents_before'] - 2

    # Aggressive transfer of 20 agents from Queue B (which causes severe deficit on Queue B)
    risky_res = sim.simulate_scenario(
        queue='Queue A',
        as_of=as_of,
        scenario_type='transfer_agents',
        agents_to_transfer=20,
        donor_queue='Queue B',
        donor_sla_floor=0.85,
    )
    assert risky_res['donor_impact'] is not None
    assert risky_res['donor_impact']['donor_floor_breached'] is True
    assert risky_res['constraint_feasible'] is False, "Scenario should be flagged as infeasible due to donor breach"
    assert len(risky_res['constraint_violations']) > 0


def test_simulation_api_endpoint():
    """RG-09: POST /api/simulations executes simulation cleanly and returns transparent math."""
    res = client.post('/api/simulations', json={
        'queue': 'Queue A',
        'as_of': '2026-09-13 16:30:00',
        'scenario_type': 'add_temporary_agents',
        'agents_to_add': 8,
        'agents_to_transfer': 0,
        'duration_hours': 4.0,
        'hourly_rate_usd': 45.0,
        'target_sla': 0.90,
    })
    assert res.status_code == 200
    data = res.json()

    assert data['agents_added'] == 8
    # Cost: 8 * 45 * 4 = 1440
    assert data['estimated_cost_usd'] == 1440.0
    assert data['projected_sla'] > 0.0
    assert data['validation_status'] == 'UNVALIDATED_STEADY_STATE_PROXY'
    assert data['model_name'] == 'ERLANG_C_CAPACITY_PROXY'
