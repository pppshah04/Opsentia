# Seven-screen desktop UX specification
**Visual direction:** Use the approved Opsentia reference mockups in `frontend/reference_mockups/`. Retain VYRA deep midnight navy, ultraviolet/blue and cyan gradients, original Opsentia product identity, VYRA team attribution. Screens must be original frontend implementations with real data, not pasted screenshot backgrounds.

## Persistent shell
Left 230–260px navigation; top current replay date/time and synthetic-mode indicator; unified search/filter; consistent label + typography scale (12/14/16 body, 20/24 headings, 30–36 KPIs). No tiny unreadable chart labels. Graceful support for 1366×768, 1440×900 and 1920×1080 desktop.

## Hierarchy
1. **Critical/high and required action** above trend/chart density.
2. State clearly when data is historical replay, current in replay, predicted or speculative.
3. Each KPI card has unit, exact queue and period, delta/reference, source tooltip.
4. Investigation has 'Live Gemini verified' if and only if a successful request used real model/API. On failure show fallback visibly.
5. Decision Lab never invents efficacy; if calibrated projection unavailable, display outcome as unavailable and let user inspect scenario assumptions.
6. Actions/Notifications separate prepared, attempted, simulated sent, failed, suppressed, acknowledged; counters and rows reconcile.
7. Historical Analytics has working intraday/week/month/long-term time windows, not just visual buttons.

## Critical controls
Time slider/replay, queue select, period select, incident filter, inspect evidence, compare scenarios, explicit approval dialog, audit timeline, history range, and 'Ask Opsentia' investigation request are connected to actual server endpoints.

## Storyboard
Start at 16:00 or 16:30 on historical synthetic incident; show warning before 17:00 threshold crossing; investigate through real Gemini, compare scenarios, acknowledge critical escalation, approve demo-only action, advance replay, and show actual observations and measured error.

## Design QA
Compare image snapshots at 1366, 1440, 1920; prevent horizontal overflow, NaN/Infinity, bogus precision, clipping and clickable inert controls. Automated browser smoke + manual interactions, screenshot evidence saved to `evidence/browser/`.
