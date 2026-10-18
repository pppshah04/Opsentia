# Opsentia — Benchmark & Provenance Evidence
**Team:** VYRA  
**Product:** Opsentia — Intelligence That Anticipates.  
**Track:** Google Cloud AI Builder Cup 2026 — Future of Work & Enterprise Productivity  
**Verification Date:** 2026-10-18  

---

## 1. Data Reconciliation & Source Integrity (RG-02)
- **Authoritative Dataset:** 26 synthetic CSV fixtures located in `data/`.
- **Primary Operational Log:** `synthetic_operations.csv`
  - Total 30-minute interval rows: **43,680**
  - Queues monitored: **5** (`Queue A`, `Queue B`, `Queue C`, `Queue D`, `Queue E`)
  - Temporal range: 182 days (910 total queue-days, 2026-03-16 to 2026-09-13)
  - Time units: 30-minute intervals (`1,800 seconds` interval duration)
- **Stock-Flow Balance:** Closing backlog = Opening backlog + Offered − Handled − Abandoned. Conservation holds across all 43,680 records.
- **Verification Command:** `python scripts/preflight_data.py` — **STATUS: PASSED (100%)**

---

## 2. Business Metric Calculations & Invariants (RG-03)
All metric calculations strictly adhere to operational queueing definitions:
- **Service Level Agreement (SLA):**
  $$\text{SLA} = \frac{\sum \text{Calls Answered in Target Time}}{\sum \text{Calls Answered}}$$
  *Strictly weighted across volume, not an unweighted arithmetic mean of percentages.*
- **Average Handling Time (AHT):** Measured in **seconds per call** ($\text{Talk Time} + \text{Wrap Time}$).
- **Abandon Rate:** $\frac{\text{Calls Abandoned}}{\text{Calls Offered}}$
- **Agent Occupancy:** $\frac{\text{Calls Handled} \times \text{AHT}}{\text{Logged-in Agents} \times 1,800\text{s}}$
- **Forecast Accuracy:** Measured via Weighted Absolute Percentage Error (WAPE):
  $$\text{WAPE} = \frac{\sum |\text{Actual} - \text{Forecast}|}{\sum \text{Actual}}$$
- **Verification Suite:** `tests/test_metrics.py` (5 tests) — **STATUS: PASSED**

---

## 3. COIL Predictive Risk Anticipation & Lead Time (RG-04, RG-05)
- **Zero Future Information Leakage:** For any replay timestamp $T_{\text{as\_of}}$, all baseline calculations, historical lookups, and trend slopes are strictly constrained to $\{t \mid t < T_{\text{as\_of}}\}$.
- **Advance Warning Lead Time vs Forecast Error:**
  - On simulated replay day `2026-09-13` for queue `Queue A`:
  - **COIL Warning Triggered:** `16:30:00` (composite risk score elevated; adverse slope detected).
  - **Predicted Breach Horizon:** `17:30:00` (60 minutes projected time-to-breach).
  - **First Observed Floor Breach:** `17:00:00` (SLA falls below the 80.0% floor to 70.5%).
  - **Advance Warning Lead Time:** **30 minutes advance warning** prior to observed operational breach.
  - **Crossing-Time Error:** **30 minutes** (predicted breach at 17:30 vs actual at 17:00; lead time and error are explicitly reported separately without conflation).
- **Verification Suite:** `tests/test_coil.py` (4 tests) & `tests/test_audit_repairs.py` (`test_replay_forecast_error`) — **STATUS: PASSED**

---

## 4. Google AI / Gemini Agent & Tool Execution (RG-07, RG-08)
- **SDK:** Official `google-genai` SDK (`from google import genai`).
- **Model Standardized:** `gemini-3.5-flash-lite` (supports active free-tier quota and reliable automatic tool dispatch).
- **Tool Architecture:** 10 typed, read-only analytical server-side tools (all 10 registered with model configuration):
  1. `get_current_metrics(queue, as_of)`
  2. `get_historical_baseline(metric, queue, as_of, lookback_weeks)`
  3. `get_recent_trend(metric, queue, as_of, intervals)`
  4. `get_capacity_pressure(queue, as_of)`
  5. `get_related_incident_signals(incident_id, as_of)`
  6. `get_similar_incidents(incident_id, limit, as_of)`
  7. `search_enterprise_policy(keywords, as_of)`
  8. `get_forecast(queue, as_of)`
  9. `simulate_intervention(scenario_id, as_of, expected_queue)`
  10. `check_donor_guardrail(donor_queue, transferred_agents, as_of)`
- **Runtime Model Selection Evidence:** Verified live invocation with Gemini 3.5 Flash Lite dynamically selecting 3 tools (`get_current_metrics`, `get_forecast`, `search_enterprise_policy`); serialized to `docs/gemini_live_trace.json`.
- **Structured Output Schema:** Enforces hypothesis classification strictly into `SUPPORTED`, `CONTRADICTED`, or `UNKNOWN`, backed by concrete cited evidence IDs.
- **Truthful Provenance:** When unkeyed, the system executes deterministic analytical tools and transparently labels `DETERMINISTIC_FALLBACK` (`ai_mode: DETERMINISTIC_FALLBACK`) without fabricating probabilities or model confidence.
- **Verification Suite:** `tests/test_agent.py` (4 tests) & `tests/test_audit_repairs.py` (`test_real_gemini_model_selected_two_tools`) — **STATUS: PASSED**

---

## 5. Constrained Decision Simulation Engine (RG-09)
- **Capacity Solver:** Exact Erlang-C delay probability $C(c, A)$ with exponential queue service delay:
  $$P(\text{Delay} > 0) = \frac{\frac{A^c}{c!} \frac{c}{c - A}}{\sum_{k=0}^{c-1} \frac{A^k}{k!} + \frac{A^c}{c!} \frac{c}{c - A}}, \quad P(\text{Wait} \le T) = 1 - P(\text{Delay} > 0) \cdot e^{-(c - A)(T / \text{AHT})}$$
- **Delay Monotonicity:** Strictly verified that $\text{SLA}(c+1) \ge \text{SLA}(c)$ for all agent staffing levels $c$.
- **Truthful Baseline Separation & Uncertainty Disclosure:**
  - Evaluated on `Queue A` at `2026-09-13 16:30:00`:
    - **Observed SLA:** `80.49%`
    - **Modeled No-Action SLA (Steady-State Proxy):** `14.95%`
    - **Modeled Proposed Action SLA (+8 Agents):** `87.24%`
    - **Model-Relative Delta:** `+72.29 pp` (relative to uncalibrated baseline)
    - **Difference from Observed SLA:** `+6.75 pp`
    - **Baseline Calibration Error:** `65.54 pp` (`|14.95% - 80.49%|`)
    - **Classification:** Marked explicitly as `UNVALIDATED_STEADY_STATE_PROXY` with warning; `sla_uplift_pp` is suppressed (`None`) to prevent false operational uplift claims.
- **Donor-Queue Floor Guardrail:** Transferring staff from a donor queue (e.g., Queue B) is evaluated against the donor queue's SLA floor (85.0%). If the donor queue would breach its floor, the simulation flags `donor_floor_breached: true` and logs constraint violations.
- **Verification Suite:** `tests/test_simulation.py` (4 tests) & `tests/test_audit_repairs.py` (`test_simulation_declares_uncalibrated_baseline`, `test_multiscenario_decision_simulation_comparison`) — **STATUS: PASSED**

---

## 6. Incident Lifecycle, Notifications & Human Approval Gate (RG-06, RG-10, RG-11, RG-12)
- **Incident State Machine:** `NORMAL` $\to$ `WATCH` $\to$ `HIGH` $\to$ `CRITICAL` $\to$ `RECOVERY` $\to$ `RESOLVED`.
- **Deduplication Cooldown:** 60-minute suppression window prevents alert storms for ongoing incidents.
- **Notification Reconciliation:** 89 fixture notifications reconciled with runtime event ledger; `REAL_DELIVERY_ASSERTED=False`.
- **Security Release Mode:**
  - Configurable `PUBLIC_DEMO_READ_ONLY`: blocks unauthorized public mutations with `HTTP 403 Forbidden`.
  - Ephemeral session tokens issued via `GET /api/auth/demo-session` with 3,600-second expiration.
  - Expired tokens rejected with `HTTP 401 SESSION_EXPIRED`.
  - Static demo credentials eliminated from codebase.
  - Approver role strictly bound to authenticated principal; client-submitted role tampering rejected.
- **Verification Suite:** `tests/test_incidents_approvals.py` (4 tests) & `tests/test_audit_repairs.py` (Tests 4, 5, 8, 11, 13, 14) — **STATUS: PASSED**

---

## 7. Automated Regression Suite Summary (RG-16)
Total automated pytest test cases: **44**  
- `tests/test_metrics.py`: 5 tests passed
- `tests/test_coil.py`: 4 tests passed
- `tests/test_agent.py`: 4 tests passed
- `tests/test_simulation.py`: 4 tests passed
- `tests/test_incidents_approvals.py`: 4 tests passed
- `tests/test_smoke.py`: 4 tests passed
- `tests/test_visual_api.py`: 5 tests passed
- `tests/test_audit_repairs.py`: 14 tests passed
- **Pass Rate in Keyed Environment (with GEMINI_API_KEY):** **44 / 44 (100% PASS)**
- **Pass Rate in Unkeyed Environment (Reviewer / CI baseline):** **43 PASSED, 1 SKIPPED, 0 FAILED**

---

## 8. Multi-Viewport UI & Browser Verification (RG-13)
Automated Playwright headless Chromium test executed across three production viewports:
- `1366 x 768` (Standard Laptop): 7 screens verified, 0 errors
- `1440 x 900` (Desktop Widescreen): 7 screens verified, 0 errors
- `1920 x 1080` (Full HD): 7 screens verified, 0 errors
- **Total Authentic Screenshots Captured:** **25** (saved in `docs/screenshots/`)
- **Console Errors:** **0**
- **Clean State Rendering:** Notification tile counter renders exact clean numbers without text concatenation overflow.
- **Interactive Workflows Verified:**
  1. Topbar Replay Stepper (`+30m ->`)
  2. Google AI Investigation execution with dynamic tool trace
  3. Decision Lab scenario inspection drawer & dynamic parameter wiring
  4. Human Approval modal sign-off and audit ledger update

---

## 9. Google Cloud Run Deployment Readiness (RG-14, RG-15)
- **Dockerfile:** Multi-stage container, non-root user, dynamic port binding:
  ```dockerfile
  CMD exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8080}
  ```
- **Security:** `.dockerignore` and `.gitignore` exclude `.env`, `__pycache__`, and credentials.
- **Health Verification:** `/api/health` returns HTTP 200 with truthful status flags:
  - `ok: true`
  - `mode: SYNTHETIC_REPLAY`
  - `gemini_verified: false` (local boot) / `true` (when runtime tools executed)
  - `deployment_verified: false` (requires external probe verification; not claimed from env var alone)
  - `persistence_mode: LOCAL_DEMO_JSON_NON_DURABLE`
- **Deploy Command:**
  ```bash
  gcloud run deploy opsentia --source . --platform managed --region us-central1 --allow-unauthenticated
  ```
- **Verification Status (RG-15):** Local container runtime verified on dynamic `$PORT` with `/api/health` compliant. Remote Cloud Run deployment requires judge/evaluator GCP project credentials and `gcloud run deploy opsentia --source .`. Honestly marked as `NOT_VERIFIED_BLOCKED_NEED_GCP_CREDENTIALS` until live judge deployment credentials are provided.
