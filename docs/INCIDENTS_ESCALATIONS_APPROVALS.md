# Incident Command, Notification Matrix and Action Records
## Incident lifecycle (persistent)
`NORMAL`→`WATCH`→`HIGH`→`CRITICAL`→`RECOVERY`→`RESOLVED`; severe breaches can jump to CRITICAL. Downgrade after configurable sustained recovery, not one good data point. Duplicate metric events append evidence to existing incident thread; don't create separate incident IDs.

Store incident_id, queue, all signal IDs, severity, owner, detected_at, predicted_breach_at (can be null), actual_breach_at (only after observed), updated_at, ack_by/at, state and reason code.

## Escalation policy and matrix
Policy data from `opsentia_escalation_matrix.csv` (synthetic demo). Example: WATCH→Real-Time team, HIGH→Real-Time+Manager/Director per configured policy, CRITICAL→Real-Time+Director/senior owner; role/channel/delay/ACK SLA/cooldown must be **read from policy rows**, not hardcoded in frontend. No automatic executive notification absent a configured rule.

## One incident → one notification thread
Event fields `event_id`, `incident_id`, `dedup_key`, `recipient_role`, `channel`, `severity`, `event_type`, `reason`, `created_at`, `attempted_at`, `delivered_at`, `acknowledged_at`, `status`, `failure_reason`, `suppression_reason`, `provider_message_id?`, `simulation_mode`, `triggered_by`.
- Differentiate `PREPARED`, `ATTEMPTED`, `SIMULATED_SENT`, `SENT_VERIFIED`, `FAILED`, `SUPPRESSED`, `ACKNOWLEDGED` using durable event rows.
- Summary count computed from ledger; **do not** sum prepared+sent+suppressed as unique notifications without specifying denominator. Count messages vs recipients separately.
- If incident upgrades, dedup cooldown must NOT suppress first critical notice to newly-required recipient role.
- Escalation updates and repeated reminders add events but preserve incident_id/thread.
- Capture dismissal, failure and acknowledgment; users can drill down to event history.
- For competition, use **simulation-only notifications** unless a genuine channel integration is both verified and safe.

## Action state machine
`PROPOSED`→`PENDING_APPROVAL`→`APPROVED|REJECTED`→`SIMULATED_IN_PROGRESS`→`SIMULATED_COMPLETED|SIMULATED_FAILED`→`OUTCOME_RECORDED`.
Valid state transitions only, with role check, optimistic concurrency, event history and idempotent request keys. No PROPOSED→COMPLETED shortcut. Persist who did what/when, expected outcome, measured observation and distinction between association versus attributable causal effect.

## Replay-clock safety
Due/overdue calculations MUST use replay clock in synthetic demo; do not mark September 2026 tasks overdue because the real calendar is October. Every view explicitly displays `as_of` from selected replay state.

## Demo endpoint acceptance
Open active incident → acknowledge → view notification counts → approve simulation → action appears as in progress → advance replay → mark observation reviewed → store outcome. Refresh browser and see preserved records (if persistent backend active). There are no real external staffing or email/SMS actions.
