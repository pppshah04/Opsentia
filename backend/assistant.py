"""Opsentia — Conversational Data Assistant (Opsentia Chat) (v3.4)
Server-side Gemini function-calling assistant for operational intelligence Q&A.
Executes bounded read-only analytical tools with citation evidence, prompt-injection defense,
grounded policy document retrieval, zero future incident leakage, and multi-turn session memory.
Team VYRA · Google Cloud AI Builder Cup 2026.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import timedelta
import pandas as pd
from pydantic import BaseModel, Field

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    genai = None
    types = None
    HAS_GENAI = False


class ChatContext(BaseModel):
    queue: str = "Queue A"
    as_of: str = "2026-09-13 16:30:00"
    grain: str = "intraday"


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., max_length=1000)
    context: Optional[ChatContext] = None
    queue: Optional[str] = None
    as_of: Optional[str] = None
    grain: Optional[str] = None


ChatRequest = ChatMessageRequest


class ChatMessageResponse(BaseModel):
    session_id: str
    turn_id: str
    answer: str
    reply: Optional[str] = None
    evidence: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    ai_mode: str
    verified: bool
    as_of: str
    caveats: List[str] = []

    def model_post_init(self, __context: Any) -> None:
        if not self.reply:
            self.reply = self.answer


def resolve_temporal_period(msg: str, as_of: str) -> Dict[str, Any]:
    """Resolve natural language time expressions to explicit start/end dates and grain without future leakage.
    Ensures 'last month' resolves to the previous completed calendar month (e.g., August 2026 for a September cutoff).
    """
    msg_lower = msg.lower()
    as_of_dt = pd.Timestamp(as_of)
    current_day = as_of[:10]

    # 1. Prior / Last Month (e.g., "last month" from 2026-09-13 means 2026-08-01 to 2026-08-31)
    if any(w in msg_lower for w in ['last month', 'prior month', 'previous month', 'past month', 'last-month']):
        first_of_cur_month = as_of_dt.replace(day=1)
        last_day_prev_month = first_of_cur_month - timedelta(days=1)
        prev_month_str = last_day_prev_month.strftime('%Y-%m')
        start_date = f"{prev_month_str}-01"
        end_date = last_day_prev_month.strftime('%Y-%m-%d')
        return {
            'resolved': True,
            'period_type': 'PRIOR_MONTH',
            'grain': 'month',
            'label': f"Prior completed calendar month: **{last_day_prev_month.strftime('%B %Y')}** ({start_date} through {end_date})",
            'period_name': last_day_prev_month.strftime('%B %Y'),
            'start_date': f"{start_date} 00:00:00",
            'end_date': f"{end_date} 23:30:00",
            'query_as_of': f"{end_date} 23:30:00",
            'is_partial': False,
        }

    # 2. Current Month / MTD (e.g., "this month", "month to date", "mtd")
    if any(w in msg_lower for w in ['this month', 'current month', 'month to date', 'mtd', 'monthly']):
        cur_month_str = as_of[:7]
        start_date = f"{cur_month_str}-01"
        return {
            'resolved': True,
            'period_type': 'CURRENT_MONTH',
            'grain': 'month',
            'label': f"Current Month-to-Date: **{as_of_dt.strftime('%B %Y')}** ({start_date} through {as_of})",
            'period_name': as_of_dt.strftime('%B %Y'),
            'start_date': f"{start_date} 00:00:00",
            'end_date': as_of,
            'query_as_of': as_of,
            'is_partial': bool(as_of_dt.day < 30 or as_of[11:16] < '23:30'),
        }

    # 3. Prior / Last Week
    if any(w in msg_lower for w in ['last week', 'prior week', 'previous week', 'past week', 'last-week']):
        cur_week_start = as_of_dt - timedelta(days=as_of_dt.weekday())
        prev_week_end = cur_week_start - timedelta(minutes=30)
        prev_week_start = cur_week_start - timedelta(days=7)
        return {
            'resolved': True,
            'period_type': 'PRIOR_WEEK',
            'grain': 'week',
            'label': f"Prior completed week ({prev_week_start.strftime('%Y-%m-%d')} to {prev_week_end.strftime('%Y-%m-%d')})",
            'period_name': prev_week_start.strftime('%G-W%V'),
            'start_date': f"{prev_week_start.strftime('%Y-%m-%d')} 00:00:00",
            'end_date': f"{prev_week_end.strftime('%Y-%m-%d')} 23:30:00",
            'query_as_of': f"{prev_week_end.strftime('%Y-%m-%d')} 23:30:00",
            'is_partial': False,
        }

    # 4. Current Week / WTD
    if any(w in msg_lower for w in ['this week', 'current week', 'week to date', 'wtd', 'weekly']):
        cur_week_start = as_of_dt - timedelta(days=as_of_dt.weekday())
        return {
            'resolved': True,
            'period_type': 'CURRENT_WEEK',
            'grain': 'week',
            'label': f"Current Week-to-Date ({as_of_dt.strftime('%G-W%V')})",
            'period_name': as_of_dt.strftime('%G-W%V'),
            'start_date': f"{cur_week_start.strftime('%Y-%m-%d')} 00:00:00",
            'end_date': as_of,
            'query_as_of': as_of,
            'is_partial': True,
        }

    # 5. Prior Day / Yesterday
    if any(w in msg_lower for w in ['yesterday', 'prior day', 'previous day', 'last day']):
        prev_day = as_of_dt - timedelta(days=1)
        prev_day_str = prev_day.strftime('%Y-%m-%d')
        return {
            'resolved': True,
            'period_type': 'PRIOR_DAY',
            'grain': 'day',
            'label': f"Prior completed day ({prev_day_str})",
            'period_name': prev_day_str,
            'start_date': f"{prev_day_str} 00:00:00",
            'end_date': f"{prev_day_str} 23:30:00",
            'query_as_of': f"{prev_day_str} 23:30:00",
            'is_partial': False,
        }

    # 6. Today / Intraday
    if any(w in msg_lower for w in ['today', 'intraday', 'current day']):
        return {
            'resolved': True,
            'period_type': 'INTRADAY',
            'grain': 'intraday',
            'label': f"Intraday ({current_day})",
            'period_name': current_day,
            'start_date': f"{current_day} 00:00:00",
            'end_date': as_of,
            'query_as_of': as_of,
            'is_partial': bool(as_of[11:16] < '23:30'),
        }

    return {'resolved': False, 'grain': None}


class OpsentiaAssistantService:
    """Conversational assistant service with model-selected tool execution."""

    def __init__(self, data_dir: str, ops_df: pd.DataFrame, analytics_service, forecast_service, watchouts_service):
        self.data_dir = data_dir
        self.ops_df = ops_df
        self.analytics = analytics_service
        self.forecast = forecast_service
        self.watchouts = watchouts_service
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}

        # Grounding data stores
        self.knowledge_df = pd.DataFrame()
        self.transfer_rules_df = pd.DataFrame()
        self.incidents_df = pd.DataFrame()

        data_path = Path(self.data_dir)
        kc_file = data_path / 'opsentia_knowledge_catalog.csv'
        if kc_file.exists():
            try:
                self.knowledge_df = pd.read_csv(kc_file)
            except Exception:
                pass

        tr_file = data_path / 'opsentia_queue_transfer_rules.csv'
        if tr_file.exists():
            try:
                self.transfer_rules_df = pd.read_csv(tr_file)
            except Exception:
                pass

        inc_file = data_path / 'opsentia_incidents.csv'
        if inc_file.exists():
            try:
                self.incidents_df = pd.read_csv(inc_file)
            except Exception:
                pass

        # Available Gemini API client
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model_id = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.client = genai.Client(api_key=self.api_key) if (HAS_GENAI and self.api_key) else None

        # Build tool definitions
        self._setup_tools()

    def _setup_tools(self):
        """Define bounded, read-only analytical tools for chat dispatch."""
        self.tool_functions = {
            'get_period_metrics': self.tool_get_period_metrics,
            'compare_periods': self.tool_compare_periods,
            'get_full_day_forecast': self.tool_get_full_day_forecast,
            'get_coil_watchouts': self.tool_get_coil_watchouts,
            'get_current_metrics': self.tool_get_current_metrics,
            'get_historical_baseline': self.tool_get_historical_baseline,
            'get_policy_document': self.tool_get_policy_document,
            'get_historical_incidents': self.tool_get_historical_incidents,
        }

    # ----------------------------------------------------
    # BOUNDED READ-ONLY TOOL IMPLEMENTATIONS
    # ----------------------------------------------------
    def tool_get_period_metrics(self, queue: str, grain: str, as_of: str) -> Dict[str, Any]:
        """Fetch call-weighted operational summary for a given horizon."""
        data = self.analytics.get_analytics(queue=queue, grain=grain, as_of=as_of)
        return {
            'result_id': f"SRC-METRICS-{queue}-{grain}-{as_of}",
            'queue': queue,
            'grain': grain,
            'as_of': as_of,
            'summary': data.get('summary'),
            'is_partial': data.get('is_partial'),
        }

    def tool_compare_periods(self, queue: str, grain: str, as_of: str) -> Dict[str, Any]:
        """Compare current period performance with prior comparable period."""
        data = self.analytics.get_analytics(queue=queue, grain=grain, as_of=as_of)
        return {
            'result_id': f"SRC-COMP-{queue}-{grain}-{as_of}",
            'comparison': data.get('comparison'),
            'warnings': data.get('warnings'),
        }

    def tool_get_full_day_forecast(self, queue: str, as_of: str) -> Dict[str, Any]:
        """Retrieve full-day EOD performance projection."""
        fc = self.forecast.get_full_day_forecast(queue=queue, as_of=as_of)
        return {
            'result_id': f"SRC-FC-EOD-{queue}-{as_of}",
            'queue': queue,
            'as_of': as_of,
            'actual_to_date': fc.get('actual_to_date'),
            'predicted_remaining': fc.get('predicted_remaining'),
            'projected_full_day': fc.get('projected_full_day'),
            'assumptions': fc.get('assumptions'),
        }

    def tool_get_coil_watchouts(self, queue: str, as_of: str, horizon: str = "all") -> Dict[str, Any]:
        """Retrieve active COIL early warning watch-outs."""
        wo_list = self.watchouts.get_watchouts(queue=queue, as_of=as_of, horizon=horizon)
        return {
            'result_id': f"SRC-WO-{queue}-{as_of}",
            'watchouts_count': len(wo_list),
            'watchouts': wo_list[:3],
        }

    def tool_get_current_metrics(self, queue: str, as_of: str) -> Dict[str, Any]:
        """Get latest observed 30-minute interval metrics."""
        q_df = self.ops_df[(self.ops_df['queue'] == queue) & (self.ops_df['timestamp'] == as_of)]
        if q_df.empty:
            q_df = self.ops_df[(self.ops_df['queue'] == queue) & (self.ops_df['timestamp'] <= as_of)].tail(1)
        if q_df.empty:
            return {'result_id': "SRC-NONE", 'error': 'No observations'}
        r = q_df.iloc[0]
        return {
            'result_id': f"SRC-OPS-{queue}-{as_of}",
            'queue': queue,
            'timestamp': str(r['timestamp']),
            'offered_calls': int(r['offered_calls']),
            'answered_calls': int(r['answered_calls']),
            'sla': round(float(r['sla']), 4),
            'sla_pct': round(float(r['sla']) * 100, 1),
            'aht': round(float(r['aht']), 1) if 'aht' in r else 280.0,
            'available_agents': int(r['available_agents']),
            'backlog': int(r['backlog']),
        }

    def tool_get_historical_baseline(self, queue: str, as_of: str) -> Dict[str, Any]:
        """Get 4-week historical same-time baseline."""
        as_of_dt = pd.Timestamp(as_of)
        hist_dates = [(as_of_dt - timedelta(days=w * 7)).strftime('%Y-%m-%d') for w in range(1, 5)]
        pool = self.ops_df[
            (self.ops_df['queue'] == queue) &
            (self.ops_df['timestamp'].str.slice(0, 10).isin(hist_dates)) &
            (self.ops_df['timestamp'].str.slice(11, 19) == as_of[11:19])
        ]
        if pool.empty:
            return {'result_id': 'SRC-BASE-EMPTY', 'note': 'No baseline matches'}
        return {
            'result_id': f"SRC-BASE-{queue}-{as_of[11:16]}",
            'baseline_sla': round(float(pool['sla'].mean()), 4),
            'baseline_volume': round(float(pool['offered_calls'].mean()), 1),
            'baseline_aht': round(float(pool['aht'].mean()), 1) if 'aht' in pool.columns else 280.0,
            'sample_periods': len(pool),
        }

    def tool_get_policy_document(self, query: str, as_of: str) -> Dict[str, Any]:
        """Search approved enterprise policies effective strictly as of replay date."""
        q_lower = query.lower()
        as_of_date = as_of[:10]

        # Donor queue transfer protection rule
        if any(w in q_lower for w in ['donor', 'transfer', 'donor queue', 'donor protection', 'donor rule', 'floor']):
            return {
                'result_id': 'SRC-POL-DONOR-RULES',
                'query': query,
                'matched_policy': {
                    'id': 'SRC-POL-DONOR-RULES',
                    'title': 'Queue Capacity Transfer & Donor Protection Rules',
                    'content': 'Cross-Queue Reallocation Policy (opsentia_queue_transfer_rules.csv): Donor queue SLA must not drop below 85.0% protected floor (protected_donor_min_sla=0.85). Maximum transferable donor capacity is capped at 20.0% of donor roster (max_donor_share_fraction=0.20). Mandatory human manager approval and availability check are required before any operational reallocation. Direct cross-skilling is enabled between Queues A, B, and C; Retention and Support L2 require explicit cross-skill training.',
                    'category': 'CAPACITY_TRANSFER',
                    'approval_status': 'APPROVED_SYNTHETIC',
                    'effective_from': '2026-03-01',
                    'effective_until': '2027-03-01',
                }
            }

        # Knowledge catalog search
        if not self.knowledge_df.empty:
            active_docs = self.knowledge_df[
                (self.knowledge_df['effective_from'] <= as_of_date) &
                (self.knowledge_df['effective_until'] >= as_of_date) &
                (self.knowledge_df['approval_status'].str.startswith('APPROVED'))
            ]

            doc_row = pd.DataFrame()
            if any(w in q_lower for w in ['escalat', 'notification', 'matrix', 'notify', 'pager']):
                doc_row = active_docs[active_docs['document_id'] == 'DOC-002']
            elif any(w in q_lower for w in ['standard', 'formula', 'calculate', 'met call', 'denominator']):
                doc_row = active_docs[active_docs['document_id'] == 'DOC-003']
            elif any(w in q_lower for w in ['human approval', 'audit', 'authorize', 'permission']):
                doc_row = active_docs[active_docs['document_id'] == 'DOC-004']
            elif any(w in q_lower for w in ['drift', 'version control', 'conflict']):
                doc_row = active_docs[active_docs['document_id'] == 'DOC-005']
            elif any(w in q_lower for w in ['campaign', 'marketing', 'planned event']):
                doc_row = active_docs[active_docs['document_id'] == 'DOC-006']
            elif any(w in q_lower for w in ['sandbox', 'simulation', 'comparator']):
                doc_row = active_docs[active_docs['document_id'] == 'DOC-007']
            elif any(w in q_lower for w in ['capacity', 'playbook', 'peak demand', 'workforce']):
                doc_row = active_docs[active_docs['document_id'] == 'DOC-001']
            else:
                q_words = set(re.findall(r'\w+', q_lower))
                best_match = None
                best_score = 0
                for _, r in active_docs.iterrows():
                    text = f"{r.get('title', '')} {r.get('content_text', '')}".lower()
                    words = set(re.findall(r'\w+', text))
                    score = len(q_words & words)
                    if score > best_score:
                        best_score = score
                        best_match = r
                if best_score > 0 and best_match is not None:
                    return {
                        'result_id': f"SRC-POL-{best_match['document_id']}",
                        'query': query,
                        'matched_policy': {
                            'id': best_match['document_id'],
                            'title': best_match['title'],
                            'content': best_match['content_text'],
                            'category': best_match.get('category', 'SOP'),
                            'approval_status': best_match.get('approval_status', 'APPROVED'),
                            'effective_from': best_match.get('effective_from', '2026-03-01'),
                            'effective_until': best_match.get('effective_until', '2027-03-01'),
                        }
                    }

            if not doc_row.empty:
                r = doc_row.iloc[0]
                return {
                    'result_id': f"SRC-POL-{r['document_id']}",
                    'query': query,
                    'matched_policy': {
                        'id': r['document_id'],
                        'title': r['title'],
                        'content': r['content_text'],
                        'category': r.get('category', 'SOP'),
                        'approval_status': r.get('approval_status', 'APPROVED'),
                        'effective_from': r.get('effective_from', '2026-03-01'),
                        'effective_until': r.get('effective_until', '2027-03-01'),
                    }
                }

        return {
            'result_id': 'SRC-POL-NO-MATCH',
            'query': query,
            'matched_policy': None,
            'note': 'NO_RELEVANT_EVIDENCE',
        }

    def tool_get_historical_incidents(self, queue: str, as_of: str) -> Dict[str, Any]:
        """Get past comparable incidents strictly prior to or active at as_of (zero future leakage).
        For active/ongoing incidents (start_at <= as_of < end_at), returns only interim observed
        metrics derived strictly from operational interval records <= as_of cutoff, hiding future outcomes.
        """
        if not self.incidents_df.empty and 'start_at' in self.incidents_df.columns:
            cond = (self.incidents_df['start_at'] <= as_of)
            if queue != 'All Queues':
                cond = cond & (self.incidents_df['queue'] == queue)
            prior_inc = self.incidents_df[cond].sort_values('start_at', ascending=False)

            inc_records = []
            for _, r in prior_inc.head(5).iterrows():
                iid = str(r['incident_id'])
                q = str(r['queue'])
                start_at = str(r['start_at'])
                end_at_val = r.get('end_at')
                end_at_str = str(end_at_val) if pd.notna(end_at_val) else None

                # Determine if incident is completed historical vs active ongoing as of cutoff
                is_active = bool(end_at_str is None or end_at_str > as_of)

                if is_active:
                    # Ongoing incident: calculate interim metrics strictly from intervals <= as_of
                    q_cond = (self.ops_df['queue'] == q) if q != 'All Queues' else True
                    act_slice = self.ops_df[
                        q_cond &
                        (self.ops_df['timestamp'] >= start_at) &
                        (self.ops_df['timestamp'] <= as_of)
                    ]
                    if not act_slice.empty:
                        interim_peak_offered = int(act_slice['offered_calls'].max())
                        interim_min_sla = round(float(act_slice['sla'].min()), 4)
                        interim_max_backlog = int(act_slice['backlog'].max())
                        interim_max_occ = round(float(act_slice['occupancy'].max()), 4) if 'occupancy' in act_slice.columns else None
                    else:
                        interim_peak_offered = 0
                        interim_min_sla = None
                        interim_max_backlog = 0
                        interim_max_occ = None

                    inc_records.append({
                        'incident_id': iid,
                        'date': start_at[:10],
                        'queue': q,
                        'incident_type': r['incident_type'],
                        'start_at': start_at,
                        'end_at': None,  # Suppress future end_at for active event
                        'peak_offered_calls': interim_peak_offered,
                        'min_sla': interim_min_sla,
                        'max_backlog': interim_max_backlog,
                        'max_occupancy': interim_max_occ,
                        'outcome_status': 'ACTIVE_ONGOING',
                        'is_active': True,
                        'status': 'ACTIVE_ONGOING',
                    })
                else:
                    # Completed historical incident: safe to report finalized metrics
                    inc_records.append({
                        'incident_id': iid,
                        'date': start_at[:10],
                        'queue': q,
                        'incident_type': r['incident_type'],
                        'start_at': start_at,
                        'end_at': end_at_str,
                        'peak_offered_calls': int(r.get('peak_offered_calls', 0)),
                        'min_sla': round(float(r['min_sla']), 4) if pd.notna(r.get('min_sla')) else None,
                        'max_backlog': int(r.get('max_backlog', 0)),
                        'max_occupancy': round(float(r['max_occupancy']), 4) if pd.notna(r.get('max_occupancy')) else None,
                        'outcome_status': r.get('outcome_status', 'RESOLVED'),
                        'is_active': False,
                        'status': r.get('outcome_status', 'RESOLVED'),
                    })

            return {
                'result_id': f"SRC-INC-HIST-{queue}",
                'as_of_cutoff': as_of,
                'count': len(inc_records),
                'incidents': inc_records,
            }

        return {
            'result_id': f"SRC-INC-NONE-{queue}",
            'as_of_cutoff': as_of,
            'count': 0,
            'incidents': [],
            'note': 'NO_RELEVANT_EVIDENCE',
        }

    # ----------------------------------------------------
    # CHAT PROCESSING WITH MULTI-TURN MEMORY
    # ----------------------------------------------------
    def chat(self, req: ChatMessageRequest) -> ChatMessageResponse:
        """Handle incoming chat message with prompt defense, memory tracking, and tool dispatch."""
        session_id = req.session_id or f"chat-sess-{uuid.uuid4().hex[:12]}"
        turn_id = f"turn-{uuid.uuid4().hex[:8]}"
        user_msg = req.message.strip()
        ctx = req.context or ChatContext()
        if req.queue:
            ctx.queue = req.queue
        if req.as_of:
            ctx.as_of = req.as_of
        if req.grain:
            ctx.grain = req.grain

        # Multi-turn session initialization
        if session_id not in self.sessions:
            self.sessions[session_id] = []

        # Record incoming turn
        self.sessions[session_id].append({
            'role': 'user',
            'message': user_msg,
            'as_of': ctx.as_of,
            'queue': ctx.queue,
            'timestamp': time.time(),
        })

        # Prompt injection defense
        injection_patterns = [
            r'ignore (all )?previous instructions',
            r'disregard (all )?rules',
            r'forget your instructions',
            r'override (system )?(guidelines|rules)',
            r'system prompt override',
            r'reveal (your )?system prompt',
            r'you are now (a|an) [a-z]+ bot',
            r'bypass (auth|security|restrictions)',
            r'sudo ',
            r'execute (command|admin)',
            r'admin shell',
            r'root access',
            r'rm -rf',
            r'drop (table|database)',
        ]
        for pat in injection_patterns:
            if re.search(pat, user_msg, re.IGNORECASE):
                resp = ChatMessageResponse(
                    session_id=session_id,
                    turn_id=turn_id,
                    answer="Security notice: System prompt overrides and shell execution requests are blocked by Opsentia enterprise policy. All queries are restricted to read-only operational analytics.",
                    evidence=[],
                    tool_calls=[],
                    ai_mode="SECURITY_GUARDRAIL_BLOCKED",
                    verified=False,
                    as_of=ctx.as_of,
                    caveats=["Adversarial prompt injection pattern detected and neutralized."],
                )
                self.sessions[session_id].append({'role': 'assistant', 'answer': resp.answer, 'timestamp': time.time()})
                return resp

        # Check / refresh Gemini client
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.client and HAS_GENAI and api_key:
            self.api_key = api_key
            self.client = genai.Client(api_key=api_key)

        if self.client and HAS_GENAI:
            response = self._chat_with_gemini(session_id, turn_id, user_msg, ctx)
        else:
            response = self._chat_deterministic_fallback(session_id, turn_id, user_msg, ctx)

        # Record assistant answer in session history (capped to last 20 messages)
        self.sessions[session_id].append({
            'role': 'assistant',
            'answer': response.answer,
            'tool_calls': response.tool_calls,
            'evidence': response.evidence,
            'timestamp': time.time(),
        })
        if len(self.sessions[session_id]) > 20:
            self.sessions[session_id] = self.sessions[session_id][-20:]

        return response

    def _chat_with_gemini(self, session_id: str, turn_id: str, user_msg: str, ctx: ChatContext) -> ChatMessageResponse:
        """Execute chat turn using official google-genai function calling."""
        executed_tool_calls: List[Dict[str, Any]] = []
        evidence_list: List[Dict[str, Any]] = []

        def get_period_metrics(queue: str, grain: str, as_of: str) -> dict:
            """Fetch call-weighted operational summary for a given horizon."""
            res = self.tool_get_period_metrics(queue, grain, as_of)
            executed_tool_calls.append({'name': 'get_period_metrics', 'arguments': {'queue': queue, 'grain': grain, 'as_of': as_of}, 'status': 'ok'})
            evidence_list.append({'source_id': res.get('result_id'), 'as_of': as_of})
            return res

        def get_full_day_forecast(queue: str, as_of: str) -> dict:
            """Retrieve full-day EOD performance projection."""
            res = self.tool_get_full_day_forecast(queue, as_of)
            executed_tool_calls.append({'name': 'get_full_day_forecast', 'arguments': {'queue': queue, 'as_of': as_of}, 'status': 'ok'})
            evidence_list.append({'source_id': res.get('result_id'), 'as_of': as_of})
            return res

        def compare_periods(queue: str, grain: str, as_of: str) -> dict:
            """Compare current period performance with prior comparable period."""
            res = self.tool_compare_periods(queue, grain, as_of)
            executed_tool_calls.append({'name': 'compare_periods', 'arguments': {'queue': queue, 'grain': grain, 'as_of': as_of}, 'status': 'ok'})
            evidence_list.append({'source_id': res.get('result_id'), 'as_of': as_of})
            return res

        def get_coil_watchouts(queue: str, as_of: str, horizon: str = "all") -> dict:
            """Retrieve active COIL early warning watch-outs."""
            res = self.tool_get_coil_watchouts(queue, as_of, horizon)
            executed_tool_calls.append({'name': 'get_coil_watchouts', 'arguments': {'queue': queue, 'as_of': as_of, 'horizon': horizon}, 'status': 'ok'})
            evidence_list.append({'source_id': res.get('result_id'), 'as_of': as_of})
            return res

        def get_current_metrics(queue: str, as_of: str) -> dict:
            """Get latest observed 30-minute interval metrics."""
            res = self.tool_get_current_metrics(queue, as_of)
            executed_tool_calls.append({'name': 'get_current_metrics', 'arguments': {'queue': queue, 'as_of': as_of}, 'status': 'ok'})
            evidence_list.append({'source_id': res.get('result_id'), 'as_of': as_of})
            return res

        def search_enterprise_policy(query: str, as_of: str) -> dict:
            """Search approved enterprise operational policies and playbooks."""
            res = self.tool_get_policy_document(query, as_of)
            executed_tool_calls.append({'name': 'search_enterprise_policy', 'arguments': {'query': query, 'as_of': as_of}, 'status': 'ok'})
            evidence_list.append({'source_id': res.get('result_id'), 'as_of': as_of})
            return res

        def get_historical_incidents(queue: str, as_of: str) -> dict:
            """Get past comparable incidents strictly prior to as_of."""
            res = self.tool_get_historical_incidents(queue, as_of)
            executed_tool_calls.append({'name': 'get_historical_incidents', 'arguments': {'queue': queue, 'as_of': as_of}, 'status': 'ok'})
            evidence_list.append({'source_id': res.get('result_id'), 'as_of': as_of})
            return res

        tools_list = [
            get_period_metrics,
            get_full_day_forecast,
            compare_periods,
            get_coil_watchouts,
            get_current_metrics,
            search_enterprise_policy,
            get_historical_incidents,
        ]

        # Assemble conversation context from prior turns in session
        prior_turns = self.sessions.get(session_id, [])[:-1]  # Exclude the current message
        history_snippet = ""
        if prior_turns:
            history_lines = [f"{t.get('role', 'user').capitalize()}: {t.get('message') or t.get('answer', '')}" for t in prior_turns[-4:]]
            history_snippet = "Recent Conversation History:\n" + "\n".join(history_lines) + "\n\n"

        prompt = (
            f"You are Opsentia AI, the operational decision intelligence assistant for Team VYRA.\n"
            f"Active Session Context: Queue='{ctx.queue}', Replay Cutoff (as_of)='{ctx.as_of}', Horizon='{ctx.grain}'.\n"
            f"{history_snippet}"
            f"User Question: '{user_msg}'\n\n"
            f"Instructions:\n"
            f"1. You MUST call relevant tools (such as get_current_metrics, get_full_day_forecast, get_period_metrics, get_coil_watchouts, compare_periods, search_enterprise_policy, get_historical_incidents) with queue='{ctx.queue}' and as_of='{ctx.as_of}' to retrieve authoritative operational data before answering.\n"
            f"2. Strict temporal integrity: all operational observations are strictly <= {ctx.as_of}. Do not hallucinate future facts.\n"
            f"3. State numerical figures with clear context, distinguish observed vs projected metrics, and cite result IDs.\n"
            f"4. Deliver a concise, grounded executive operational response."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=tools_list,
                    temperature=0.2,
                )
            )

            answer_text = response.text or "Analysis completed based on retrieved analytical evidence."

            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                answer=answer_text,
                evidence=evidence_list,
                tool_calls=executed_tool_calls,
                ai_mode="GEMINI_LIVE",
                verified=True,
                as_of=ctx.as_of,
                caveats=["Grounded in operational synthetic fixtures strictly <= as_of cutoff."],
            )

        except Exception as e:
            fb = self._chat_deterministic_fallback(session_id, turn_id, user_msg, ctx)
            fb.caveats.append(f"Live Gemini API note: {str(e)[:120]}. Served via grounded deterministic analytical fallback.")
            return fb

    def _chat_deterministic_fallback(self, session_id: str, turn_id: str, user_msg: str, ctx: ChatContext) -> ChatMessageResponse:
        """Deterministic analytical Q&A routing when Gemini is unconfigured or unavailable."""
        msg_lower = user_msg.lower()
        tool_calls: List[Dict[str, Any]] = []
        evidence: List[Dict[str, Any]] = []

        # Resolve temporal period from message (handles 'last month', 'this month', 'last week', 'yesterday')
        t_period = resolve_temporal_period(user_msg, ctx.as_of)
        target_grain = t_period['grain'] if t_period['resolved'] else ctx.grain
        query_as_of = t_period.get('query_as_of', ctx.as_of) if t_period['resolved'] else ctx.as_of

        # 1. Historical incidents query
        if 'incident' in msg_lower or 'historical breach' in msg_lower or 'past breach' in msg_lower:
            inc_res = self.tool_get_historical_incidents(ctx.queue, ctx.as_of)
            tool_calls.append({'name': 'get_historical_incidents', 'status': 'ok'})
            evidence.append({'source_id': inc_res['result_id'], 'as_of': ctx.as_of})
            incs = inc_res.get('incidents', [])
            if incs:
                active_incs = [i for i in incs if i.get('is_active')]
                completed_incs = [i for i in incs if not i.get('is_active')]
                sections = []
                if active_incs:
                    act_lines = [
                        f"- **{i['incident_id']} ({i['date']}):** {i['incident_type']} (Started {i['start_at'][11:16]}) | Observed Interim Peak Offered: {i['peak_offered_calls']} | Observed Interim Min SLA: {round((i['min_sla'] or 0)*100, 2)}% | Max Backlog: {i['max_backlog']} | Status: ACTIVE_ONGOING (In progress as of {ctx.as_of[11:16]})"
                        for i in active_incs
                    ]
                    sections.append(f"**Active / Ongoing Incidents as of {ctx.as_of}:**\n" + "\n".join(act_lines))
                if completed_incs:
                    comp_lines = [
                        f"- **{i['incident_id']} ({i['date']}):** {i['incident_type']} | Peak Offered: {i['peak_offered_calls']} | Min SLA: {round((i['min_sla'] or 0)*100, 1)}% | Status: {i['outcome_status']}"
                        for i in completed_incs
                    ]
                    sections.append(f"**Resolved Historical Incidents:**\n" + "\n".join(comp_lines))
                answer = f"Operational incidents for **{ctx.queue}** recorded prior to or active at {ctx.as_of}:\n\n" + "\n\n".join(sections)
            else:
                answer = f"No historical or active incidents on record for **{ctx.queue}** prior to {ctx.as_of} (Evidence: NO_RELEVANT_EVIDENCE)."

        # 2. Policy query (including donor queue protection)
        elif any(w in msg_lower for w in ['policy', 'rule', 'donor', 'escalat', 'transfer', 'matrix', 'sop']):
            pol_res = self.tool_get_policy_document(user_msg, ctx.as_of)
            tool_calls.append({'name': 'get_policy_document', 'status': 'ok'})
            evidence.append({'source_id': pol_res['result_id'], 'as_of': ctx.as_of})
            mp = pol_res.get('matched_policy')
            if mp:
                answer = f"**Enterprise Policy Reference:** {mp.get('title')} (`{mp.get('id')}`)\n\n{mp.get('content')}"
            else:
                answer = f"No matching enterprise policy document found for query: '{user_msg}' effective as of {ctx.as_of[:10]}."

        # 3. Monthly / period summary if explicitly requested
        elif (t_period.get('resolved') and t_period.get('grain') == 'month') or (target_grain == 'month' and any(w in msg_lower for w in ['month', 'monthly', 'what happened', 'performance'])):
            m_res = self.tool_get_period_metrics(ctx.queue, 'month', query_as_of)
            tool_calls.append({'name': 'get_period_metrics', 'arguments': {'queue': ctx.queue, 'grain': 'month', 'as_of': query_as_of}, 'status': 'ok'})
            evidence.append({'source_id': m_res['result_id'], 'as_of': query_as_of})
            s = m_res.get('summary', {})
            comp_res = self.tool_compare_periods(ctx.queue, 'month', query_as_of)
            c = comp_res.get('comparison', {})

            if t_period.get('period_type') == 'PRIOR_MONTH':
                answer = (
                    f"Monthly operational summary for **{ctx.queue}** ({t_period['label']}):\n"
                    f"- **Completed Month SLA:** {s.get('sla_pct')}%\n"
                    f"- **Total Offered Calls:** {s.get('offered_calls'):,}\n"
                    f"- **Total Answered Calls:** {s.get('answered_calls'):,}\n"
                    f"- **Average AHT:** {s.get('aht_seconds')}s\n"
                    f"- **Average Agents:** {s.get('avg_available_agents')}\n"
                    f"- **End Backlog:** {s.get('end_backlog')} calls\n"
                    f"- **Month-over-Month Delta:** SLA change {c.get('sla_delta_pp', 'N/A')} pp, volume change {c.get('volume_change_pct', 'N/A')}%."
                )
            else:
                answer = (
                    f"Monthly operational summary for **{ctx.queue}** as of **{ctx.as_of}** (Month-to-Date):\n"
                    f"- **MTD SLA:** {s.get('sla_pct')}%\n"
                    f"- **MTD Offered Calls:** {s.get('offered_calls'):,}\n"
                    f"- **MTD Answered Calls:** {s.get('answered_calls'):,}\n"
                    f"- **Average AHT:** {s.get('aht_seconds')}s\n"
                    f"- **Average Agents:** {s.get('avg_available_agents')}\n"
                    f"- **Current Backlog:** {s.get('end_backlog')} calls\n"
                    f"- **Month-over-Month Delta:** SLA change {c.get('sla_delta_pp', 'N/A')} pp, volume change {c.get('volume_change_pct', 'N/A')}%."
                )

        # 4. Forecast / EOD projection
        elif 'forecast' in msg_lower or 'project' in msg_lower or 'eod' in msg_lower or 'full-day' in msg_lower:
            fc_res = self.tool_get_full_day_forecast(ctx.queue, ctx.as_of)
            tool_calls.append({'name': 'get_full_day_forecast', 'status': 'ok'})
            evidence.append({'source_id': fc_res['result_id'], 'as_of': ctx.as_of})
            p = fc_res.get('projected_full_day', {})
            act = fc_res.get('actual_to_date', {})

            # Dynamic backtest MAE retrieval
            bt = self.forecast.backtest_full_day(queue=ctx.queue, as_of=ctx.as_of, eval_days=7)
            mae_pp = bt.get('mean_absolute_error_sla_pp', 0.0)
            eval_window = bt.get('evaluation_window_days', 0)

            answer = (
                f"For **{ctx.queue}** as of **{ctx.as_of}**:\n"
                f"- **Observed-to-date SLA:** {act.get('sla_pct')}% across {act.get('intervals_count')} intervals ({act.get('offered_calls')} offered calls).\n"
                f"- **Projected Full-Day (EOD) SLA:** **{p.get('sla_pct')}%** (target: 90.0%).\n"
                f"- **Projected Total Offered Volume:** {p.get('offered_calls')} calls.\n"
                f"- **Projected End Backlog:** {p.get('end_backlog')} calls.\n"
                f"- **Uncertainty & Risk:** Risk Level `{p.get('risk_level', 'NORMAL')}` (Heuristic Scenario Range: {p.get('sla_lower_pct')}% - {p.get('sla_upper_pct')}%).\n\n"
                f"**Assumptions:** Projection combines observed counts with prior 4-week same-weekday baselines and capacity stock-flow models. Empirical walk-forward backtest MAE for {ctx.queue} is {mae_pp} pp across {eval_window} evaluated days."
            )

        # 5. Active COIL watch-outs
        elif 'watch' in msg_lower or 'alert' in msg_lower or 'risk' in msg_lower:
            wo_res = self.tool_get_coil_watchouts(ctx.queue, ctx.as_of, horizon=target_grain)
            tool_calls.append({'name': 'get_coil_watchouts', 'status': 'ok'})
            evidence.append({'source_id': wo_res['result_id'], 'as_of': ctx.as_of})
            wos = wo_res.get('watchouts', [])
            if wos:
                lines = [f"- **[{w['severity']}] {w['metric']} ({w['horizon']}):** {w['reason']} *(Evidence: {', '.join(w['evidence_ids'])})*" for w in wos]
                answer = f"Active COIL Watch-Outs for **{ctx.queue}** ({target_grain} horizon):\n\n" + "\n".join(lines)
            else:
                answer = f"No active operational watch-outs detected for **{ctx.queue}** as of {ctx.as_of}."

        # 6. Period comparison
        elif 'compare' in msg_lower or 'versus' in msg_lower or 'vs' in msg_lower:
            comp_res = self.tool_compare_periods(ctx.queue, target_grain, ctx.as_of)
            tool_calls.append({'name': 'compare_periods', 'status': 'ok'})
            evidence.append({'source_id': comp_res['result_id'], 'as_of': ctx.as_of})
            c = comp_res.get('comparison', {})
            answer = (
                f"Comparison for **{ctx.queue}** ({target_grain} horizon) vs {c.get('comparison_label')}:\n"
                f"- Prior Period SLA: {c.get('prior_period_sla_pct')}%\n"
                f"- SLA Delta: {c.get('sla_delta_pp')} pp\n"
                f"- Workload Volume Change: {c.get('volume_change_pct')}%\n"
                f"- AHT Delta: {c.get('aht_delta_sec')} seconds"
            )

        # 7. Default operational metrics
        else:
            met_res = self.tool_get_period_metrics(ctx.queue, target_grain, ctx.as_of)
            tool_calls.append({'name': 'get_period_metrics', 'status': 'ok'})
            evidence.append({'source_id': met_res['result_id'], 'as_of': ctx.as_of})
            s = met_res.get('summary', {})
            answer = (
                f"Operational summary for **{ctx.queue}** ({target_grain} horizon) through **{ctx.as_of}**:\n"
                f"- **SLA:** {s.get('sla_pct')}%\n"
                f"- **Offered Calls:** {s.get('offered_calls')}\n"
                f"- **Answered Calls:** {s.get('answered_calls')}\n"
                f"- **Average AHT:** {s.get('aht_seconds')}s\n"
                f"- **Average Agents:** {s.get('avg_available_agents')}\n"
                f"- **End Backlog:** {s.get('end_backlog')} calls"
            )

        return ChatMessageResponse(
            session_id=session_id,
            turn_id=turn_id,
            answer=answer,
            evidence=evidence,
            tool_calls=tool_calls,
            ai_mode="DETERMINISTIC_FALLBACK",
            verified=False,
            as_of=ctx.as_of,
            caveats=["Evaluated using deterministic analytical engine strictly through as_of cutoff."],
        )
