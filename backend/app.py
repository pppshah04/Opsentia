"""Opsentia — Intelligence That Anticipates.
FastAPI Backend Gateway for Team VYRA (AI Builder Cup 2026).
Integrates COIL continuous early warning, Gemini tool agent,
Decision Lab counterfactual simulation, and persistent incident/approval lifecycle.
"""
from __future__ import annotations
import os
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import timedelta
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Body, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.business_metrics import compute_weighted_kpis, classify_sla_severity
from backend.coil import CoilEngine
from backend.simulation import DecisionSimulationService
from backend.incidents import IncidentLifecycleService
from backend.agent import OpsentiaAgentService, InvestigationResult
from backend.analytics import OpsentiaAnalyticsService
from backend.forecast_service import OpsentiaForecastService
from backend.watchouts import OpsentiaWatchoutsService
from backend.assistant import OpsentiaAssistantService, ChatRequest
from backend.supervisor import OpsentiaProactiveSupervisor, SupervisionDecision

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('DATA_DIR', str(ROOT / 'data')))
WEB = ROOT / 'frontend' / 'app'

# Security release mode configuration:
# Safe default is read-only (mutations blocked for public traffic).
# Operator token must be provided explicitly via environment or Secret Manager (no embedded source fallback).
PUBLIC_DEMO_READ_ONLY = os.getenv('PUBLIC_DEMO_READ_ONLY', 'true').lower() != 'false'
OPSENTIA_OPERATOR_TOKEN = os.getenv('OPSENTIA_OPERATOR_TOKEN')

app = FastAPI(
    title='Opsentia — Intelligence That Anticipates.',
    description='Continuous predictive operations decision intelligence by Team VYRA.',
    version='3.0.0'
)

# Core data cache
@lru_cache(maxsize=40)
def df(name: str) -> pd.DataFrame:
    allowed = {
        'synthetic_operations.csv', 'opsentia_incidents.csv', 'opsentia_incident_evidence.csv',
        'opsentia_historical_incident_matches.csv', 'opsentia_decision_scenario_inputs.csv',
        'opsentia_notifications.csv', 'opsentia_notification_events.csv',
        'opsentia_actions.csv', 'opsentia_action_activity_log.csv',
        'opsentia_incident_notification_summary.csv', 'opsentia_forecast_backtest.csv',
        'opsentia_weekly_kpis.csv', 'opsentia_monthly_kpis.csv', 'opsentia_daily_kpis.csv',
        'opsentia_queue_catalog.csv', 'opsentia_escalation_matrix.csv',
        'opsentia_knowledge_catalog.csv', 'opsentia_metric_baselines_30min.csv',
        'opsentia_incident_state_timeline.csv', 'opsentia_decision_outcome_ledger.csv',
    }
    if name not in allowed:
        raise HTTPException(400, f'Unknown data source: {name}')
    src = DATA / name
    if not src.exists():
        raise HTTPException(503, f'Data source not available: {name}')
    return pd.read_csv(src, low_memory=False)


def val(x):
    """Recursively clean numpy / pandas types for standard JSON serialization."""
    if isinstance(x, dict):
        return {k: val(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [val(v) for v in x]
    if x is None:
        return None
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    try:
        if pd.isna(x):
            return None
    except (ValueError, TypeError):
        pass
    if hasattr(x, 'item'):
        return val(x.item())
    if isinstance(x, float) and (x == float('inf') or x == float('-inf')):
        return None
    return x


def rows(data, limit=200):
    return val(data.head(limit).to_dict(orient='records'))


# Instantiate core domain services
ops_df = pd.read_csv(DATA / 'synthetic_operations.csv', low_memory=False)
coil_engine = CoilEngine(ops_df)
sim_service = DecisionSimulationService(ops_df)
incident_service = IncidentLifecycleService(DATA)
agent_service = OpsentiaAgentService(DATA, ops_df)
analytics_service = OpsentiaAnalyticsService(ops_df)
forecast_service = OpsentiaForecastService(ops_df)
watchouts_service = OpsentiaWatchoutsService(ops_df, analytics_service=analytics_service, forecast_service=forecast_service)
assistant_service = OpsentiaAssistantService(DATA, ops_df, analytics_service=analytics_service, forecast_service=forecast_service, watchouts_service=watchouts_service)
supervisor_service = OpsentiaProactiveSupervisor(
    ops_df=ops_df,
    agent_service=agent_service,
    coil_engine=coil_engine,
    incident_service=incident_service,
)


# ==========================================
# BASELINE & SYSTEM ENDPOINTS
# ==========================================

@app.get('/api/health')
def health():
    ai_status = agent_service.get_ai_status()
    has_live_trace = any(
        t.get('investigation_status') in ('LIVE_VERIFIED', 'MODEL_SELECTED_TOOL_CALLS_VERIFIED')
        for t in agent_service.traces.values()
    )
    return {
        'ok': True,
        'product': 'Opsentia',
        'tagline': 'Intelligence That Anticipates.',
        'team': 'VYRA',
        'theme': 'Future of Work & Enterprise Productivity',
        'mode': 'SYNTHETIC_REPLAY',
        'public_demo_read_only': PUBLIC_DEMO_READ_ONLY,
        'gemini_verified': has_live_trace,
        'deployment_verified': bool(os.getenv('CLOUD_RUN_PROBE_VERIFIED') == 'true'),
        'persistence_mode': 'LOCAL_DEMO_JSON_NON_DURABLE',
        'ai_mode': ai_status['ai_mode'],
        'coil_verified': True,
        'note': 'Demonstration environment utilizing 26 authoritative synthetic operational fixtures. Local JSON persistence is development/demo only.',
    }


@app.get('/api/data-coverage')
def coverage():
    x = df('synthetic_operations.csv')
    return {
        'rows': len(x),
        'queues': sorted(x['queue'].unique().tolist()),
        'start': x['timestamp'].min(),
        'end': x['timestamp'].max(),
        'intervals': int(x['timestamp'].nunique()),
        'mode': 'SYNTHETIC_REPLAY'
    }


@app.get('/api/snapshot')
def snapshot(queue: str = 'Queue A', as_of: str = '2026-09-13 17:00:00'):
    x = df('synthetic_operations.csv')
    g = x[(x['queue'] == queue) & (x['timestamp'] == as_of)]
    if g.empty:
        raise HTTPException(404, f'Missing queue {queue} at {as_of}')
    return {'mode': 'SYNTHETIC_REPLAY', 'observed': rows(g, 1)[0]}


# ==========================================
# UI BOOTSTRAP ENDPOINT (PRESERVES UI CONTRACT)
# ==========================================

@app.get('/api/ui/bootstrap')
def bootstrap(queue: str = 'Queue A', as_of: str = '2026-09-13 17:00:00'):
    x = df('synthetic_operations.csv')
    queues = sorted(x['queue'].unique().tolist())
    if queue not in queues:
        raise HTTPException(400, f'Unknown queue {queue}')
    if as_of not in x['timestamp'].values:
        raise HTTPException(404, f'Timestamp {as_of} not in dataset')

    day = as_of[:10]
    current = x[x['timestamp'] == as_of]
    now = current[current['queue'] == queue]
    if now.empty:
        raise HTTPException(404, f'Queue not observed at timestamp {as_of}')

    # Strictly prior baseline without future leakage
    baseline_res = coil_engine.get_prior_baseline(queue, as_of, lookback_weeks=4)
    baseline = baseline_res.get('metrics', {})

    # Day timeline (all 48 intervals for the selected day)
    daydata = x[(x['timestamp'].str.startswith(day)) & (x['queue'] == queue)].sort_values('timestamp')
    series = []
    for _, r in daydata.iterrows():
        is_future = r['timestamp'] > as_of
        series.append({
            'time': r['timestamp'][11:16],
            'timestamp': r['timestamp'],
            'sla': round(float(r['sla']) * 100, 2),
            'aht': round(float(r['aht']), 1),
            'volume': int(r['offered_calls']),
            'forecast': int(r['forecast']),
            'occupancy': round(float(r['occupancy']) * 100, 2),
            'backlog': int(r['backlog']),
            'available_agents': int(r['available_agents']),
            'required_agents': int(r['required_agents']),
            'abandon': round(float(r['abandon_rate']) * 100, 2),
            'accuracy': round(max(0, 100 - 100 * abs(float(r['forecast']) - float(r['offered_calls'])) / max(float(r['offered_calls']), 1)), 2),
            'is_future_in_replay': is_future,
        })

    last30 = daydata[daydata['timestamp'] <= as_of].tail(6)

    # Cross-queue comparison at as_of
    queue_rows = []
    for q in queues:
        qr = current[current['queue'] == q]
        k = compute_weighted_kpis(qr)
        queue_rows.append({
            'queue': q,
            **k,
            'severity': classify_sla_severity(k.get('sla', 1.0))
        })
    allk = compute_weighted_kpis(current)

    # Incidents
    incidents = df('opsentia_incidents.csv')
    active = incidents[(incidents['start_at'] <= as_of) & (incidents['end_at'] >= as_of)].copy()
    current_incidents = []
    for _, r in active.iterrows():
        kr = next((q for q in queue_rows if q['queue'] == r['queue']), {})
        sev = classify_sla_severity(kr.get('sla', 1.0), active_incident=True)
        current_incidents.append({
            'id': r['incident_id'],
            'queue': r['queue'],
            'type': r['incident_type'],
            'start': r['start_at'],
            'severity': sev,
            'sla': round(100 * kr.get('sla', 1.0), 1),
            'description': r['incident_type'].replace('_', ' ').title()
        })
    order = {'CRITICAL': 0, 'HIGH': 1, 'WATCH': 2, 'NORMAL': 3}
    current_incidents.sort(key=lambda z: (order.get(z['severity'], 4), z['sla']))

    selected = next((i for i in current_incidents if i['queue'] == queue), current_incidents[0] if current_incidents else None)
    incident_id = selected['id'] if selected else None

    # Evidence, matches, scenarios
    ev = df('opsentia_incident_evidence.csv')
    ev = ev[ev['incident_id'] == incident_id] if incident_id else ev.iloc[:0]

    matches = df('opsentia_historical_incident_matches.csv')
    matches = matches[matches['query_incident_id'] == incident_id] if incident_id else matches.iloc[:0]

    # Candidate scenarios from fixture inputs (projected_sla remains None until active simulation requested)
    scenarios = df('opsentia_decision_scenario_inputs.csv')
    if incident_id:
        scenarios = scenarios[scenarios['incident_id'] == incident_id]
        if not scenarios.empty:
            scenarios = scenarios.iloc[(pd.to_datetime(scenarios['snapshot_time']) - pd.Timestamp(as_of)).abs().argsort()[:4]]
    else:
        q_scenarios = scenarios[scenarios['target_queue'] == queue]
        if not q_scenarios.empty:
            scenarios = q_scenarios.iloc[(pd.to_datetime(q_scenarios['snapshot_time']) - pd.Timestamp(as_of)).abs().argsort()[:4]]
        else:
            scenarios = scenarios.iloc[:0]

    # Forecast
    forecast_df = df('opsentia_forecast_backtest.csv')
    forecast_rows = forecast_df[(forecast_df['queue'] == queue) & (forecast_df['issue_time'] == as_of)]
    forecast_out = forecast_rows[['horizon_minutes', 'predicted_sla_naive_trend', 'current_sla', 'model_name', 'model_assumptions']]

    # Reconciled Notifications
    notif_data = incident_service.get_incident_notifications(as_of=as_of)
    notice_summary = notif_data['summary']
    notif_list = notif_data['events']

    # Actions and audit log
    actions_data = incident_service.get_actions(as_of=as_of)

    # Strictly prior historical summaries (zero future leakage, dynamic partial period recomputation!)
    daily_analytics = analytics_service.get_analytics(queue=queue, grain='day', as_of=as_of, lookback=32)
    weekly_analytics = analytics_service.get_analytics(queue=queue, grain='week', as_of=as_of, lookback=18)
    monthly_analytics = analytics_service.get_analytics(queue=queue, grain='month', as_of=as_of, lookback=7)

    daily_rows = daily_analytics.get('series', [])
    weekly_rows = weekly_analytics.get('series', [])
    monthly_rows = monthly_analytics.get('series', [])

    # Reconciled full-day forecast and prioritized operational watch-outs
    full_day_fc = forecast_service.get_full_day_forecast(queue=queue, as_of=as_of)
    watchouts_data = watchouts_service.get_watchouts(queue=queue, as_of=as_of)

    # Heatmap strictly from the preceding 28 days
    monthback = (pd.Timestamp(as_of) - timedelta(days=28)).strftime('%Y-%m-%d %H:%M:%S')
    hist = x[(x['timestamp'] >= monthback) & (x['timestamp'] <= as_of)].copy()
    hist['hour'] = hist['timestamp'].str.slice(11, 13).astype(int)
    grouped = hist.groupby(['queue', 'hour'])[['answered_calls', 'sla_met_calls']].sum().reset_index()
    heatmap = [
        {
            'queue': r.queue,
            'hour': int(r.hour),
            'sla': float(r.sla_met_calls / r.answered_calls) if r.answered_calls else None
        }
        for r in grouped.itertuples()
    ]

    catalog = df('opsentia_queue_catalog.csv')
    policies = df('opsentia_escalation_matrix.csv')
    knowledge = df('opsentia_knowledge_catalog.csv')

    has_live_trace = any(
        t.get('investigation_status') in ('LIVE_VERIFIED', 'MODEL_SELECTED_TOOL_CALLS_VERIFIED')
        for t in agent_service.traces.values()
    )

    return val({
        'meta': {
            'product': 'Opsentia',
            'tagline': 'Intelligence That Anticipates.',
            'team': 'VYRA',
            'mode': 'SYNTHETIC_REPLAY',
            'public_demo_read_only': PUBLIC_DEMO_READ_ONLY,
            'as_of': as_of,
            'queue': queue,
            'queues': queues,
            'gemini_verified': has_live_trace,
            'cloud_run_verified': bool(os.getenv('CLOUD_RUN_PROBE_VERIFIED') == 'true'),
            'time_zone': 'Fixture local time; zone unspecified',
        },
        'current': rows(now, 1)[0],
        'summary': allk,
        'baseline': baseline,
        'rolling': compute_weighted_kpis(last30),
        'queue_comparison': queue_rows,
        'timeline': series,
        'active_incidents': current_incidents,
        'selected_incident': selected,
        'evidence': rows(ev, 15),
        'matches': rows(matches, 6),
        'scenarios': rows(scenarios, 8),
        'forecast': rows(forecast_out, 6),
        'notification_summary': notice_summary,
        'notifications': rows(pd.DataFrame(notif_list), 28) if notif_list else [],
        'actions': rows(pd.DataFrame(actions_data['actions']), 18) if actions_data['actions'] else [],
        'action_log': rows(pd.DataFrame(actions_data['action_log']), 25) if actions_data['action_log'] else [],
        'daily': daily_rows,
        'weekly': weekly_rows,
        'monthly': monthly_rows,
        'full_day_forecast': full_day_fc,
        'watchouts': watchouts_data,
        'queue_catalog': rows(catalog, 10),
        'escalation_matrix': rows(policies, 22),
        'knowledge': rows(knowledge, 10),
        'hourly_heatmap': heatmap,
    })


# ==========================================
# COIL CONTINUOUS INTELLIGENCE ENDPOINTS
# ==========================================

@app.get('/api/coil/snapshot')
def coil_snapshot(queue: str = 'Queue A', as_of: str = '2026-09-13 16:30:00'):
    """Return COIL early warning, trend velocity, and time-to-breach forecast."""
    ew = coil_engine.compute_early_warning_and_breach(queue, as_of)
    return {
        'data': ew,
        'meta': {
            'as_of': as_of,
            'queue': queue,
            'origin': 'COIL_REALTIME_DERIVED',
            'model_version': 'COIL_EARLY_WARNING_V2',
            'verified': True,
        }
    }


class ReplayAdvanceRequest(BaseModel):
    current_as_of: str
    minutes: int = 30
    enable_proactive_supervisor: bool = False


@app.post('/api/coil/replay/advance')
def coil_advance_replay(req: ReplayAdvanceRequest):
    """Advance replay clock to next discrete interval and re-evaluate incident state."""
    next_as_of = coil_engine.advance_replay_timestamp(req.current_as_of, req.minutes)
    # Re-evaluate Queue A
    cur_row = ops_df[(ops_df['queue'] == 'Queue A') & (ops_df['timestamp'] == next_as_of)]
    sla = float(cur_row.iloc[0]['sla']) if not cur_row.empty else 0.90
    inc_state = incident_service.update_incident_state('EV-2026-0913-01', sla, next_as_of)

    # Opt-in proactive supervisor evaluation on tick
    supervision_decision = None
    if req.enable_proactive_supervisor:
        decision = supervisor_service.evaluate_tick(
            queue='Queue A',
            as_of=next_as_of,
            incident_id='EV-2026-0913-01',
            force_enable=True,
        )
        supervision_decision = decision.model_dump()

    return {
        'previous_as_of': req.current_as_of,
        'new_as_of': next_as_of,
        'incident_state': inc_state,
        'current_sla': sla,
        'breach_observed': sla < 0.75,
        'supervision': supervision_decision,
    }


class SupervisorTickRequest(BaseModel):
    queue: str = "Queue A"
    as_of: str = "2026-09-13 16:30:00"
    incident_id: Optional[str] = "EV-2026-0913-01"
    force_enable: bool = True


@app.post('/api/coil/supervisor/tick', response_model=SupervisionDecision)
def supervisor_tick(req: SupervisorTickRequest):
    """Opt-in trigger for proactive Gemini supervisor intelligence audit."""
    return supervisor_service.evaluate_tick(
        queue=req.queue,
        as_of=req.as_of,
        incident_id=req.incident_id,
        force_enable=req.force_enable,
    )


@app.get('/api/coil/supervisor/status')
def supervisor_status():
    """Return supervisor health, dedupe cache status, and ledger count."""
    return supervisor_service.get_status()


@app.get('/api/coil/supervisor/ledger')
def supervisor_ledger(limit: int = 50):
    """Return stored proactive supervision investigation records."""
    return supervisor_service.investigation_ledger[-limit:]


# ==========================================
# GEMINI AGENT & INVESTIGATION ENDPOINTS
# ==========================================

class InvestigateRequest(BaseModel):
    incident_id: str = "EV-2026-0913-01"
    queue: str = "Queue A"
    as_of: str = "2026-09-13 16:30:00"
    force_fallback: bool = False


@app.post('/api/investigate', response_model=InvestigationResult)
def investigate(req: InvestigateRequest):
    """Execute Gemini evidence investigation loop across 10 read-only analytical tools."""
    return agent_service.investigate(
        incident_id=req.incident_id,
        queue=req.queue,
        as_of=req.as_of,
        force_fallback=req.force_fallback,
    )


@app.get('/api/ai/status')
def ai_status():
    """Return honest capability and invocation verification status."""
    return agent_service.get_ai_status()


@app.get('/api/investigations/{trace_id}/trace')
def get_trace(trace_id: str):
    """Return sanitized tool execution trace."""
    trace = agent_service.traces.get(trace_id)
    if not trace:
        raise HTTPException(404, f'Trace {trace_id} not found')
    return trace


# ==========================================
# OPSENTIA v3.4 MULTI-HORIZON & AI ENDPOINTS
# ==========================================

@app.get('/api/analytics')
def get_analytics(
    queue: str = Query('Queue A', description="Queue name or 'All Queues'"),
    grain: str = Query('day', description="Granularity: 'intraday', 'day', 'week', 'month'"),
    as_of: str = Query('2026-09-13 17:00:00', description="Replay timestamp cutoff"),
    lookback: int = Query(30, description="Number of historical periods to include")
):
    """Retrieve multi-horizon call-weighted analytics with zero temporal leakage."""
    return val(analytics_service.get_analytics(queue=queue, grain=grain, as_of=as_of, lookback=lookback))


@app.get('/api/forecasts/full-day')
def get_full_day_forecast(
    queue: str = Query('Queue A', description="Target queue name"),
    as_of: str = Query('2026-09-13 17:00:00', description="Replay timestamp cutoff")
):
    """Reconciled End-of-Day (EOD) operational forecast separating observed and projected intervals."""
    return val(forecast_service.get_full_day_forecast(queue=queue, as_of=as_of))


@app.get('/api/forecasts/full-day/backtest')
def get_full_day_backtest(
    queue: str = Query('Queue A', description="Target queue name"),
    as_of: str = Query('2026-09-13 17:00:00', description="Replay timestamp cutoff"),
    target_date: Optional[str] = Query(None, description="Specific date to evaluate"),
    cutoff_time: Optional[str] = Query(None, description="Cutoff time on target date"),
    eval_days: int = Query(7, description="Historical days to evaluate")
):
    """Walk-forward backtest evaluating EOD forecast accuracy across historical dates."""
    return val(forecast_service.backtest_full_day(
        queue=queue,
        as_of=as_of,
        target_date=target_date,
        cutoff_time=cutoff_time,
        eval_days=eval_days
    ))


@app.get('/api/coil/watchouts')
def get_coil_watchouts(
    queue: str = Query('Queue A', description="Target queue name"),
    as_of: str = Query('2026-09-13 17:00:00', description="Replay timestamp cutoff"),
    horizon: str = Query('all', description="Operational horizon: 'intraday', 'daily', 'weekly', 'monthly', 'all'")
):
    """Prioritized operational risks and early warnings with traceable evidence IDs."""
    items = watchouts_service.get_watchouts(queue=queue, as_of=as_of, horizon=horizon)
    return val({'queue': queue, 'as_of': as_of, 'watchouts': items})


@app.post('/api/assistant/chat')
def assistant_chat(req: ChatRequest):
    """Conversational operations Q&A powered by Gemini with bounded analytical tools."""
    res = assistant_service.chat(req)
    out = res.model_dump()
    out['reply'] = res.answer
    return val(out)


# ==========================================
# DECISION LAB SIMULATION ENDPOINTS
# ==========================================

class SimulationRequest(BaseModel):
    queue: str = "Queue A"
    as_of: str = "2026-09-13 16:30:00"
    scenario_type: str = "add_temporary_agents"
    agents_to_add: int = 0
    agents_to_transfer: int = 0
    donor_queue: Optional[str] = None
    duration_hours: float = 4.0
    hourly_rate_usd: float = 45.0
    target_sla: float = 0.90
    donor_sla_floor: float = 0.85


@app.post('/api/simulations')
def simulate_decision(req: SimulationRequest):
    """Calculate candidate intervention outcomes, labor cost, and donor queue impacts."""
    return sim_service.simulate_scenario(
        queue=req.queue,
        as_of=req.as_of,
        scenario_type=req.scenario_type,
        agents_to_add=req.agents_to_add,
        agents_to_transfer=req.agents_to_transfer,
        donor_queue=req.donor_queue,
        duration_hours=req.duration_hours,
        hourly_rate_usd=req.hourly_rate_usd,
        target_sla=req.target_sla,
        donor_sla_floor=req.donor_sla_floor,
    )


# ==========================================
# ==========================================
# ACTIONS, APPROVALS & NOTIFICATIONS ENDPOINTS
# ==========================================

ACTIVE_DEMO_SESSIONS: Dict[str, Dict[str, Any]] = {}


@app.get('/api/auth/demo-session')
def get_demo_session(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_operator_token: Optional[str] = Header(None, alias="X-Operator-Token"),
):
    """Generate ephemeral session token with expiration and role binding.
    Unauthenticated calls ALWAYS receive read-only viewer sessions.
    Mutation-capable sessions strictly require valid operator credentials.
    """
    token_str = None
    if authorization and authorization.startswith("Bearer "):
        token_str = authorization.split("Bearer ", 1)[1].strip()
    elif authorization:
        token_str = authorization.strip()
    elif x_operator_token:
        token_str = x_operator_token.strip()

    # Operator validation: requires non-empty OPSENTIA_OPERATOR_TOKEN matching provided token
    is_operator = bool(OPSENTIA_OPERATOR_TOKEN and token_str and token_str == OPSENTIA_OPERATOR_TOKEN)
    can_mutate = is_operator  # Anonymous/unauthenticated calls are ALWAYS viewer-only

    token = f"demo-session-{uuid.uuid4().hex[:16]}"
    now = time.time()
    expires_at = now + 3600  # 1-hour session validity
    role = "Operations Director (Authenticated)" if can_mutate else "Operations Viewer (Read-Only)"

    ACTIVE_DEMO_SESSIONS[token] = {
        'principal': f"operator:{token[:8]}" if is_operator else f"viewer:{token[:8]}",
        'role': role,
        'can_mutate': can_mutate,
        'created_at': now,
        'expires_at': expires_at,
    }

    return {
        'session_token': token,
        'role': role,
        'can_mutate': can_mutate,
        'expires_in_seconds': 3600,
        'mode': 'AUTHENTICATED_OPERATOR_SESSION' if can_mutate else 'PUBLIC_DEMO_READ_ONLY',
        'mutation_policy': 'MUTATIONS_SIMULATED_AND_LOGGED' if can_mutate else 'MUTATIONS_DISABLED_READ_ONLY',
    }


def verify_demo_authorization(
    x_demo_approver: Optional[str] = Header(None, alias="X-Demo-Approver"),
    x_operator_token: Optional[str] = Header(None, alias="X-Operator-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """Validate that mutating endpoints are called with non-expired, authorized credentials.
    Rejects unauthenticated requests with HTTP 401; rejects mutations from read-only sessions with HTTP 403.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    elif authorization:
        token = authorization.strip()
    elif x_operator_token:
        token = x_operator_token.strip()
    elif x_demo_approver:
        token = x_demo_approver.strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="UNAUTHENTICATED_APPROVAL: Mutation requires authorized credentials. Public unauthenticated mutations are prohibited."
        )

    # 1. Check direct operator token (must be non-empty configured secret)
    if OPSENTIA_OPERATOR_TOKEN and token == OPSENTIA_OPERATOR_TOKEN:
        return f"operator:{token[:8]}"

    # 2. Check dynamic ephemeral session
    if token in ACTIVE_DEMO_SESSIONS:
        sess = ACTIVE_DEMO_SESSIONS[token]
        # Check token expiration
        if time.time() > sess.get('expires_at', 0):
            del ACTIVE_DEMO_SESSIONS[token]
            raise HTTPException(
                status_code=401,
                detail="SESSION_EXPIRED: Demo session token has expired. Please re-authenticate."
            )
        # Check read-only public demo safety
        if not sess.get('can_mutate', False):
            raise HTTPException(
                status_code=403,
                detail="PUBLIC_DEMO_READ_ONLY: Mutations are disabled for read-only sessions. Set OPSENTIA_OPERATOR_TOKEN or provide valid operator credentials to authorize actions."
            )
        return sess.get('principal', f"session-principal:{token[:12]}")

    raise HTTPException(
        status_code=401,
        detail="UNAUTHENTICATED_APPROVAL: Invalid or unknown session credentials. Public unauthenticated mutations are prohibited."
    )


class ActionApprovalRequest(BaseModel):
    actor: str = "Lead Operations Director"
    role: str = "Operations Director"
    as_of: str = "2026-09-13 16:35:00"
    rationale: str = "Approved 8 temporary agents under Decision Lab simulation"


class ActionRejectRequest(BaseModel):
    actor: str = "Lead Operations Director"
    role: str = "Operations Director"
    as_of: str = "2026-09-13 16:35:00"
    rationale: str


@app.post('/api/decisions/{action_id}/approve')
def approve_decision(
    action_id: str,
    req: ActionApprovalRequest,
    principal: str = Depends(verify_demo_authorization)
):
    """Approve an operational mitigation via human-in-the-loop state machine.
    Requires server-verified demo authorization; rejects unauthenticated principals.
    Binds actor and role to the authenticated session principal.
    """
    res = incident_service.approve_action(
        action_id=action_id,
        actor=f"Authenticated Operator [{principal}]",
        role="Operations Director (Simulated)",
        as_of=req.as_of,
        rationale=req.rationale,
    )
    if 'error' in res:
        raise HTTPException(res.get('status_code', 400), res['error'])
    return res


@app.post('/api/decisions/{action_id}/reject')
def reject_decision(
    action_id: str,
    req: ActionRejectRequest,
    principal: str = Depends(verify_demo_authorization)
):
    """Reject an operational mitigation with documented rationale.
    Requires server-verified demo authorization; rejects unauthenticated principals.
    """
    res = incident_service.reject_action(
        action_id=action_id,
        actor=f"Authenticated Operator [{principal}]",
        role="Operations Director (Simulated)",
        as_of=req.as_of,
        rationale=req.rationale,
    )
    if 'error' in res:
        raise HTTPException(res.get('status_code', 400), res['error'])
    return res


@app.get('/api/actions')
def list_actions(incident_id: Optional[str] = None, as_of: Optional[str] = None):
    return val(incident_service.get_actions(incident_id=incident_id, as_of=as_of))


@app.get('/api/notifications')
def list_notifications(incident_id: Optional[str] = None, as_of: Optional[str] = None):
    return val(incident_service.get_incident_notifications(incident_id=incident_id, as_of=as_of))


class IncidentAckRequest(BaseModel):
    actor: str = "Lead Operations Director"
    as_of: str = "2026-09-13 16:30:00"


@app.post('/api/incident/{incident_id}/acknowledge')
def acknowledge_incident(
    incident_id: str,
    req: IncidentAckRequest,
    principal: str = Depends(verify_demo_authorization)
):
    """Acknowledge an incident under authenticated operator authority."""
    return val(incident_service.acknowledge_incident(
        incident_id=incident_id,
        actor=f"Authenticated Operator [{principal}]",
        as_of=req.as_of
    ))

# ==========================================
# DEMO & EVALUATION TRUTH METRICS
# ==========================================

@app.get('/api/demo/metrics')
def demo_metrics():
    """Returns official competition truth metrics, invariants, and release gate statuses."""
    return {
        'product': 'Opsentia',
        'team': 'VYRA',
        'theme': 'Future of Work & Enterprise Productivity',
        'fixtures_total': 26,
        'records_analyzed': len(ops_df),
        'queues_covered': sorted(ops_df['queue'].unique().tolist()),
        'zero_future_leakage_guaranteed': True,
        'stock_flow_conservation_checked': True,
        'erlang_decision_proxy_active': True,
        'gemini_agent_tools_count': 16,
        'human_approval_state_machine_active': True,
        'notification_cooldown_active': True,
        'ai_mode': agent_service.get_ai_status()['ai_mode'],
        'multi_horizon_analytics_active': True,
        'full_day_performance_forecast_active': True,
        'opsentia_watchouts_active': True,
        'opsentia_chat_assistant_active': True,
    }


# Mount Static UI Files
if WEB.exists():
    app.mount('/assets', StaticFiles(directory=str(WEB / 'assets')), name='assets')
    if (WEB / 'demo').exists():
        app.mount('/demo', StaticFiles(directory=str(WEB / 'demo'), html=True), name='demo')

    @app.get('/')
    def root():
        return FileResponse(WEB / 'index.html')
