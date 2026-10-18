"""Opsentia Incident Command, Notification Ledger & Action Approval Engine.
Implements the persistent event ledger, escalation matrix routing,
deduplication/cooldown, and human approval state machine.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd


class IncidentLifecycleService:
    """Manages incident state transitions, escalation policies, notifications and actions."""

    def __init__(self, data_dir: Any):
        self.data_dir = Path(data_dir) if isinstance(data_dir, str) else data_dir
        self.runtime_file = self.data_dir / 'runtime_events.json'
        self.escalation_matrix: List[Dict[str, Any]] = []
        self._load_escalation_matrix()

        # In-memory and durable event stores for runtime / demo mode
        self.incidents: Dict[str, Dict[str, Any]] = {}
        self.notification_events: List[Dict[str, Any]] = []
        self.actions: Dict[str, Dict[str, Any]] = {}
        self.action_logs: List[Dict[str, Any]] = []

        self._seed_from_fixtures()
        self._load_runtime_state()

    def _load_escalation_matrix(self):
        matrix_path = self.data_dir / 'opsentia_escalation_matrix.csv'
        if matrix_path.exists():
            df = pd.read_csv(matrix_path)
            self.escalation_matrix = df.to_dict(orient='records')

    def _seed_from_fixtures(self):
        # Seed initial incidents from fixture
        inc_path = self.data_dir / 'opsentia_incidents.csv'
        if inc_path.exists():
            df = pd.read_csv(inc_path)
            for _, r in df.iterrows():
                iid = str(r['incident_id'])
                self.incidents[iid] = {
                    'incident_id': iid,
                    'queue': r['queue'],
                    'incident_type': r['incident_type'],
                    'start_at': r['start_at'],
                    'end_at': r['end_at'],
                    'severity': r.get('severity', 'WATCH'),
                    'state': 'WATCH',
                    'owner_role': 'Real-Time Operations Lead',
                    'acknowledged_at': None,
                    'acknowledged_by': None,
                    'normal_streak': 0,
                    'updated_at': r['start_at'],
                }

        # Seed initial actions from fixture
        act_path = self.data_dir / 'opsentia_actions.csv'
        if act_path.exists():
            df = pd.read_csv(act_path)
            for _, r in df.iterrows():
                aid = str(r['action_id'])
                self.actions[aid] = {
                    'action_id': aid,
                    'incident_id': r.get('incident_id', 'EV-2026-0913-01'),
                    'action_type': r['action_type'],
                    'owner_role': r.get('owner_role', 'Real-Time Lead'),
                    'approval_required': int(r.get('approval_required', 1)),
                    'approval_status': r.get('approval_status', 'APPROVED'),
                    'execution_status': r.get('execution_status', 'SIMULATED_COMPLETED'),
                    'created_at': r.get('created_at', '2026-09-13 16:30:00'),
                    'approved_at': r.get('action_at', '2026-09-13 16:35:00'),
                    'approved_by': 'Demo Operations Director',
                    'rationale': r.get('rationale', 'Pre-configured mitigation'),
                    'projected_sla': r.get('projected_sla', None),
                    'observed_change_pp': r.get('observed_change_pp', None),
                    'is_historical_fixture': True,
                }

        # Seed historical notification events from fixture
        notif_path = self.data_dir / 'opsentia_notification_events.csv'
        if notif_path.exists():
            df = pd.read_csv(notif_path)
            for _, r in df.iterrows():
                nid = str(r['notification_id'])
                lat = r.get('delivery_latency_seconds', 0)
                lat_sec = 0 if pd.isna(lat) else int(float(lat))
                self.notification_events.append({
                    'event_id': nid,
                    'incident_id': str(r['incident_id']),
                    'recipient_role': str(r['recipient_role']),
                    'channel': str(r['channel']),
                    'severity': str(r.get('event_reason', 'WATCH')),
                    'delivery_status': str(r['delivery_status']),
                    'event_reason': str(r['event_reason']),
                    'timestamp': str(r['timestamp']),
                    'delay_minutes': lat_sec // 60,
                    'simulation_mode': True,
                    'is_historical_fixture': True,
                })

    def _load_runtime_state(self):
        if self.runtime_file.exists():
            try:
                with open(self.runtime_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for k, v in data.get('actions', {}).items():
                    self.actions[k] = v
                for item in data.get('action_logs', []):
                    if item not in self.action_logs:
                        self.action_logs.append(item)
                for item in data.get('notification_events', []):
                    if item not in self.notification_events:
                        self.notification_events.append(item)
            except Exception as e:
                print(f"[Opsentia Persistence] Warning: failed to load runtime events: {e}")

    def _save_runtime_state(self):
        try:
            runtime_actions = {
                k: v for k, v in self.actions.items()
                if not v.get('is_historical_fixture', False) or v.get('approval_status') in ('APPROVED', 'REJECTED')
            }
            runtime_notifs = [e for e in self.notification_events if not e.get('is_historical_fixture', False)]
            data = {
                'actions': runtime_actions,
                'action_logs': self.action_logs,
                'notification_events': runtime_notifs,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
            with open(self.runtime_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Opsentia Persistence] Warning: failed to save runtime events: {e}")

    def update_incident_state(
        self,
        incident_id: str,
        current_sla: float,
        as_of: str
    ) -> Dict[str, Any]:
        """Update incident state respecting hysteresis and automatic escalation."""
        inc = self.incidents.get(incident_id)
        if not inc:
            # Create dynamic incident if unknown
            inc = {
                'incident_id': incident_id,
                'queue': 'Queue A',
                'incident_type': 'capacity_strain',
                'start_at': as_of,
                'end_at': as_of,
                'severity': 'WATCH',
                'state': 'WATCH',
                'owner_role': 'Real-Time Operations Lead',
                'acknowledged_at': None,
                'acknowledged_by': None,
                'normal_streak': 0,
                'updated_at': as_of,
            }
            self.incidents[incident_id] = inc

        old_sev = inc['severity']

        # Severity determination
        if current_sla < 0.75:
            new_sev = 'CRITICAL'
            new_state = 'CRITICAL'
            inc['normal_streak'] = 0
        elif current_sla < 0.85:
            new_sev = 'HIGH'
            new_state = 'HIGH'
            inc['normal_streak'] = 0
        elif current_sla < 0.90:
            new_sev = 'WATCH'
            new_state = 'WATCH'
            inc['normal_streak'] = 0
        else:
            # Recovery hysteresis: requires 2 consecutive normal intervals
            inc['normal_streak'] = inc.get('normal_streak', 0) + 1
            if inc['normal_streak'] >= 2:
                new_sev = 'NORMAL'
                new_state = 'RESOLVED'
            else:
                new_sev = 'WATCH'
                new_state = 'RECOVERY'

        inc['severity'] = new_sev
        inc['state'] = new_state
        inc['updated_at'] = as_of

        # If upgraded to HIGH or CRITICAL, trigger notifications
        if new_sev in ('HIGH', 'CRITICAL') and new_sev != old_sev:
            self.route_notifications(incident_id, new_sev, as_of)

        return inc

    def acknowledge_incident(self, incident_id: str, actor: str, as_of: str) -> Dict[str, Any]:
        """Acknowledge incident by human operator."""
        inc = self.incidents.get(incident_id)
        if not inc:
            inc = {
                'incident_id': incident_id,
                'queue': 'Queue A',
                'incident_type': 'capacity_strain',
                'start_at': as_of,
                'end_at': as_of,
                'severity': 'WATCH',
                'state': 'WATCH',
                'owner_role': 'Real-Time Operations Lead',
                'acknowledged_at': None,
                'acknowledged_by': None,
                'normal_streak': 0,
                'updated_at': as_of,
            }
            self.incidents[incident_id] = inc

        inc['acknowledged_at'] = as_of
        inc['acknowledged_by'] = actor
        inc['state'] = 'ACKNOWLEDGED' if inc['state'] == 'WATCH' else inc['state']

        # Append ack event to notifications
        ack_event = {
            'event_id': f'NTF-ACK-{uuid.uuid4().hex[:6]}',
            'incident_id': incident_id,
            'recipient_role': 'Command Center',
            'channel': 'IN_APP',
            'delivery_status': 'ACKNOWLEDGED',
            'event_reason': f'Acknowledged by {actor}',
            'timestamp': as_of,
            'simulation_mode': True,
        }
        self.notification_events.append(ack_event)
        return inc

    def route_notifications(
        self,
        incident_id: str,
        severity: str,
        as_of: str
    ) -> List[Dict[str, Any]]:
        """Evaluate escalation matrix for the incident severity and emit deduplicated events."""
        matching_rules = [
            r for r in self.escalation_matrix
            if r.get('severity') == severity and int(r.get('enabled', 1)) == 1
        ]
        created_events = []
        as_of_dt = pd.Timestamp(as_of)

        for rule in matching_rules:
            role = rule['recipient_role']
            channel = rule['channel']
            cooldown_min = int(rule.get('dedup_cooldown_minutes', 60))

            recent_sent = [
                e for e in self.notification_events
                if e['incident_id'] == incident_id and
                   e['recipient_role'] == role and
                   e['channel'] == channel and
                   e['delivery_status'] == 'SIMULATED_SENT' and
                   e.get('timestamp', '') < as_of
            ]

            is_suppressed = False
            suppression_reason = None

            if recent_sent:
                last_time = pd.Timestamp(recent_sent[-1]['timestamp'])
                time_diff_min = (as_of_dt - last_time).total_seconds() / 60.0
                if time_diff_min < cooldown_min:
                    is_suppressed = True
                    suppression_reason = f'Cooldown active ({int(time_diff_min)}m < {cooldown_min}m)'

            event_id = f'NTF-{uuid.uuid4().hex[:8].upper()}'
            status = 'SIMULATED_SUPPRESSED' if is_suppressed else 'SIMULATED_SENT'

            event = {
                'event_id': event_id,
                'incident_id': incident_id,
                'recipient_role': role,
                'channel': channel,
                'severity': severity,
                'delivery_status': status,
                'event_reason': suppression_reason or f'{severity} severity alert dispatched',
                'timestamp': as_of,
                'delay_minutes': int(rule.get('delay_minutes', 0)),
                'simulation_mode': True,
                'is_historical_fixture': False,
            }
            self.notification_events.append(event)
            created_events.append(event)

        self._save_runtime_state()
        return created_events

    def get_incident_notifications(
        self,
        incident_id: Optional[str] = None,
        as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch notification events and reconciled summary counts."""
        events = list(self.notification_events)
        if incident_id:
            events = [e for e in events if e.get('incident_id') == incident_id]
        if as_of:
            events = [e for e in events if e.get('timestamp') <= as_of]

        # Summary reconciliation
        summary = {
            'TOTAL_EVENTS': len(events),
            'FIXTURE_EVENTS': len([e for e in events if e.get('is_historical_fixture')]),
            'RUNTIME_SIMULATED_EVENTS': len([e for e in events if not e.get('is_historical_fixture')]),
            'SIMULATED_SENT': len([e for e in events if e.get('delivery_status') == 'SIMULATED_SENT']),
            'SIMULATED_FAILED': len([e for e in events if e.get('delivery_status') == 'SIMULATED_FAILED']),
            'SIMULATED_SUPPRESSED': len([e for e in events if e.get('delivery_status') == 'SIMULATED_SUPPRESSED']),
            'ACKNOWLEDGED': len([e for e in events if e.get('delivery_status') == 'ACKNOWLEDGED']),
            'REAL_DELIVERY_ASSERTED': False,
            'DELIVERY_MODE': 'SIMULATED_DISPATCH_ONLY',
        }

        return {
            'incident_id': incident_id,
            'summary': summary,
            'events': sorted(events, key=lambda x: x['timestamp'], reverse=True),
            'governance_note': 'Notification events are protocol dispatch simulations; external delivery to Slack/Email/Teams is NOT asserted in simulation mode.',
        }

    def create_action(
        self,
        incident_id: str,
        action_type: str,
        owner_role: str,
        rationale: str,
        projected_sla: Optional[float] = None,
        as_of: str = '2026-09-13 16:30:00'
    ) -> Dict[str, Any]:
        """Draft a candidate mitigation action."""
        action_id = f'ACT-{uuid.uuid4().hex[:8].upper()}'
        action = {
            'action_id': action_id,
            'incident_id': incident_id,
            'action_type': action_type,
            'owner_role': owner_role,
            'approval_required': 1,
            'approval_status': 'PENDING_APPROVAL',
            'execution_status': 'PROPOSED',
            'created_at': as_of,
            'approved_at': None,
            'approved_by': None,
            'rationale': rationale,
            'projected_sla': projected_sla,
            'observed_change_pp': None,
            'is_historical_fixture': False,
        }
        self.actions[action_id] = action

        # Log activity
        self.action_logs.append({
            'log_id': f'LOG-{uuid.uuid4().hex[:6]}',
            'action_id': action_id,
            'event_type': 'ACTION_PROPOSED',
            'event_at': as_of,
            'details': f'Action drafted: {action_type}',
        })
        self._save_runtime_state()
        return action

    def approve_action(
        self,
        action_id: str,
        actor: str,
        role: str,
        as_of: str,
        rationale: str = 'Approved based on Decision Lab simulation'
    ) -> Dict[str, Any]:
        """Approve action through validated state machine transition."""
        action = self.actions.get(action_id)
        if not action:
            return {'error': f'Action {action_id} not found', 'status_code': 404}

        # Check valid state transition
        if action['approval_status'] not in ('PENDING_APPROVAL', 'PROPOSED'):
            return {
                'error': f'Cannot approve action with status {action["approval_status"]}',
                'status_code': 409
            }

        # Update state
        action['approval_status'] = 'APPROVED'
        action['approval_mode'] = 'SIMULATED_APPROVAL'
        action['governance_note'] = 'Simulated operational approval under authorized demo role; not external execution'
        action['execution_status'] = 'SIMULATED_IN_PROGRESS'
        action['approved_at'] = as_of
        action['approved_by'] = f'{actor} ({role})'
        action['rationale'] = rationale

        self.action_logs.append({
            'log_id': f'LOG-{uuid.uuid4().hex[:6]}',
            'action_id': action_id,
            'event_type': 'ACTION_APPROVED',
            'event_at': as_of,
            'details': f'Approved by {actor} as {role}',
        })
        self._save_runtime_state()
        return action

    def reject_action(
        self,
        action_id: str,
        actor: str,
        role: str,
        as_of: str,
        rationale: str
    ) -> Dict[str, Any]:
        """Reject an action."""
        action = self.actions.get(action_id)
        if not action:
            return {'error': f'Action {action_id} not found', 'status_code': 404}

        if action['approval_status'] not in ('PENDING_APPROVAL', 'PROPOSED'):
            return {
                'error': f'Cannot reject action with status {action["approval_status"]}',
                'status_code': 409
            }

        action['approval_status'] = 'REJECTED'
        action['approval_mode'] = 'SIMULATED_REJECTION'
        action['execution_status'] = 'CANCELLED'
        action['approved_at'] = as_of
        action['approved_by'] = f'{actor} ({role})'
        action['rationale'] = f'REJECTED: {rationale}'

        self.action_logs.append({
            'log_id': f'LOG-{uuid.uuid4().hex[:6]}',
            'action_id': action_id,
            'event_type': 'ACTION_REJECTED',
            'event_at': as_of,
            'details': f'Rejected by {actor}: {rationale}',
        })
        self._save_runtime_state()
        return action

    def get_actions(
        self,
        incident_id: Optional[str] = None,
        as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch all action records and associated audit log."""
        acts = list(self.actions.values())
        if incident_id:
            acts = [a for a in acts if a.get('incident_id') == incident_id]
        if as_of:
            acts = [a for a in acts if a.get('created_at') <= as_of]

        logs = list(self.action_logs)
        if as_of:
            logs = [l for l in logs if l.get('event_at') <= as_of]

        return {
            'actions': sorted(acts, key=lambda x: x.get('created_at', ''), reverse=True),
            'action_log': sorted(logs, key=lambda x: x.get('event_at', ''), reverse=True),
        }
