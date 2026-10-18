"""Opsentia — Proactive Gemini Intelligence Supervisor (v3.5)
Event-driven / scheduled worker that monitors deterministic COIL telemetry,
detects meaningful operational state transitions / forecast materiality,
and launches bounded Gemini investigative audits with deduplication and cooldown.
Team VYRA · Google Cloud AI Builder Cup 2026.
"""
from __future__ import annotations
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from pydantic import BaseModel, Field

from backend.coil import CoilEngine
from backend.incidents import IncidentLifecycleService
from backend.agent import OpsentiaAgentService, InvestigationResult


class SupervisionDecision(BaseModel):
    supervisor_enabled: bool
    triggered: bool
    reason: str
    as_of: str
    queue: str
    incident_id: Optional[str] = None
    severity: Optional[str] = None
    dedupe_key: Optional[str] = None
    trace_id: Optional[str] = None
    investigation: Optional[Dict[str, Any]] = None
    autonomous_changes_made: bool = False
    human_approval_required: bool = True
    disclaimer: str = (
        "Proactive supervisor generates read-only investigative hypotheses and watch-outs. "
        "No operational actions or external alerts are dispatched without human operator approval."
    )


class OpsentiaProactiveSupervisor:
    """Continuous intelligence supervisor monitoring COIL state transitions."""

    def __init__(
        self,
        ops_df: pd.DataFrame,
        agent_service: OpsentiaAgentService,
        coil_engine: CoilEngine,
        incident_service: IncidentLifecycleService,
        enabled: Optional[bool] = None,
        cooldown_minutes: int = 60,
    ):
        self.ops_df = ops_df
        self.agent_service = agent_service
        self.coil = coil_engine
        self.incident_service = incident_service

        # Opt-in worker configuration: defaults to False unless env or flag explicitly enables
        env_flag = os.getenv("OPSENTIA_PROACTIVE_SUPERVISOR", "0").lower() in ("1", "true", "yes", "enabled")
        self.enabled = enabled if enabled is not None else env_flag
        self.cooldown_minutes = cooldown_minutes

        # State tracking: deduplication cache (incident_id, severity, time_bucket)
        self.dedupe_cache: Dict[str, Dict[str, Any]] = {}
        self.last_run_timestamp: Dict[str, str] = {}
        self.investigation_ledger: List[Dict[str, Any]] = []
        self.total_evaluations: int = 0
        self.total_triggers: int = 0

    def evaluate_tick(
        self,
        queue: str = "Queue A",
        as_of: str = "2026-09-13 16:30:00",
        incident_id: Optional[str] = None,
        force_enable: bool = False,
        custom_ai_client: Optional[Any] = None,
    ) -> SupervisionDecision:
        """Evaluate operational tick. Deterministic COIL always runs;
        meaningful state transitions or forecast materiality launch bounded Gemini investigation.
        """
        self.total_evaluations += 1
        active = self.enabled or force_enable

        # 1. Deterministic COIL always evaluates first
        ew = self.coil.compute_early_warning_and_breach(queue, as_of)
        target_incident_id = incident_id or 'EV-2026-0913-01'

        # Current telemetry snapshot for queue
        cur_row = self.ops_df[(self.ops_df['queue'] == queue) & (self.ops_df['timestamp'] == as_of)]
        current_sla = float(cur_row.iloc[0]['sla']) if not cur_row.empty else ew['current_sla']

        # Determine current severity from incident service or telemetry
        inc = self.incident_service.incidents.get(target_incident_id)
        if inc:
            severity = inc.get('severity', 'WATCH')
        else:
            if current_sla < 0.75:
                severity = 'CRITICAL'
            elif current_sla < 0.85:
                severity = 'HIGH'
            elif current_sla < 0.90:
                severity = 'WATCH'
            else:
                severity = 'NORMAL'

        # If supervisor is not enabled, return deterministic COIL status truthfully
        if not active:
            return SupervisionDecision(
                supervisor_enabled=False,
                triggered=False,
                reason="SKIPPED_SUPERVISOR_DISABLED",
                as_of=as_of,
                queue=queue,
                incident_id=target_incident_id,
                severity=severity,
            )

        # 2. Materiality check: is there a meaningful state transition or acute breach risk?
        is_severe = severity in ('HIGH', 'CRITICAL')
        is_breach_predicted = bool(ew.get('predicted_breach')) and (ew.get('time_to_breach_minutes', 999) <= 60)
        is_material = is_severe or is_breach_predicted

        if not is_material:
            return SupervisionDecision(
                supervisor_enabled=True,
                triggered=False,
                reason="INSIGNIFICANT_INTERVAL",
                as_of=as_of,
                queue=queue,
                incident_id=target_incident_id,
                severity=severity,
            )

        # 3. Deduplication check: key = (incident_id, severity, timestamp_bucket)
        time_bucket = as_of[:16]  # e.g., '2026-09-13 16:30'
        dedupe_key = f"{target_incident_id}:{severity}:{time_bucket}"

        if dedupe_key in self.dedupe_cache:
            prev = self.dedupe_cache[dedupe_key]
            return SupervisionDecision(
                supervisor_enabled=True,
                triggered=False,
                reason="DEDUPLICATED",
                as_of=as_of,
                queue=queue,
                incident_id=target_incident_id,
                severity=severity,
                dedupe_key=dedupe_key,
                trace_id=prev.get('trace_id'),
            )

        # 4. Cooldown check: prevent thrashing unless severity escalated to CRITICAL
        if target_incident_id in self.last_run_timestamp and severity != 'CRITICAL':
            last_ts = pd.Timestamp(self.last_run_timestamp[target_incident_id])
            cur_ts = pd.Timestamp(as_of)
            elapsed_min = abs((cur_ts - last_ts).total_seconds()) / 60.0
            if elapsed_min < self.cooldown_minutes:
                return SupervisionDecision(
                    supervisor_enabled=True,
                    triggered=False,
                    reason="COOLDOWN_ACTIVE",
                    as_of=as_of,
                    queue=queue,
                    incident_id=target_incident_id,
                    severity=severity,
                    dedupe_key=dedupe_key,
                )

        # 5. Launch bounded Gemini investigative workflow (budget: 1 per tick)
        trigger_reason = (
            f"State transition materiality detected: severity={severity}, "
            f"current_sla={round(current_sla * 100, 1)}%, "
            f"time_to_breach={ew.get('time_to_breach_minutes')}m"
        )

        inv_result = self.agent_service.investigate(
            incident_id=target_incident_id,
            queue=queue,
            as_of=as_of,
            ai_client=custom_ai_client,
        )

        self.dedupe_cache[dedupe_key] = {
            'trace_id': inv_result.trace_id,
            'as_of': as_of,
            'severity': severity,
            'timestamp': time.time(),
        }
        self.last_run_timestamp[target_incident_id] = as_of
        self.total_triggers += 1

        ledger_entry = {
            'supervision_id': f"SUP-{uuid.uuid4().hex[:8].upper()}",
            'as_of': as_of,
            'queue': queue,
            'incident_id': target_incident_id,
            'severity': severity,
            'dedupe_key': dedupe_key,
            'trigger_reason': trigger_reason,
            'trace_id': inv_result.trace_id,
            'ai_mode': inv_result.ai_mode,
            'summary': inv_result.executive_summary,
            'hypotheses_count': len(inv_result.hypotheses),
            'tools_executed': len(inv_result.tool_calls),
            'autonomous_changes_made': False,
            'human_approval_required': True,
        }
        self.investigation_ledger.append(ledger_entry)

        return SupervisionDecision(
            supervisor_enabled=True,
            triggered=True,
            reason=trigger_reason,
            as_of=as_of,
            queue=queue,
            incident_id=target_incident_id,
            severity=severity,
            dedupe_key=dedupe_key,
            trace_id=inv_result.trace_id,
            investigation=inv_result.model_dump(),
            autonomous_changes_made=False,
            human_approval_required=True,
        )

    def get_status(self) -> Dict[str, Any]:
        """Return proactive supervisor health, cache statistics, and ledger summary."""
        return {
            'supervisor_enabled': self.enabled,
            'cooldown_minutes': self.cooldown_minutes,
            'total_evaluations': self.total_evaluations,
            'total_triggers': self.total_triggers,
            'dedupe_entries': len(self.dedupe_cache),
            'ledger_records': len(self.investigation_ledger),
            'autonomous_execution_allowed': False,
            'safety_contract': 'HUMAN_APPROVAL_MANDATORY',
        }
