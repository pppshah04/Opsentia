# Opsentia — Intelligence That Anticipates.

**Team:** VYRA  
**Challenge:** Google Cloud AI Builder Cup 2026  
**Track:** Future of Work & Enterprise Productivity  
**Status:** Complete Functional Prototype (30/30 Unit Tests Passed, 100% Data Integrity Reconciled)  

---

## 1. Overview
Traditional contact center and operations dashboards only tell managers what already went wrong. Chatbots offer ungrounded guesses. **Opsentia** connects predictive risk anticipation to evidence-grounded AI investigations, constrained decision simulations, and human-in-the-loop governance.

Opsentia continuously monitors multi-queue operational streams, anticipates SLA breaches before they occur, investigates underlying root causes using server-side Google AI tools, models alternate intervention scenarios with donor-queue guardrails, and records auditable human approvals and verified outcomes.

---

## 2. Core Architecture & Capabilities

```
  ┌─────────────────────────────────────────────────────────────┐
  │                 7-Screen Desktop Application                │
  │   Live Intelligence  •  All Metrics  •  Investigation       │
  │   Decision Lab  •  Actions & Approvals  •  Notifications    │
  │                   Historical Analytics                      │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ REST API
  ┌──────────────────────────────┴──────────────────────────────┐
  │               FastAPI + Pydantic Backend Server             │
  │                                                             │
  │  ┌──────────────────┐  ┌────────────────┐  ┌─────────────┐  │
  │  │   COIL Engine    │  │   Google AI    │  │  Decision   │  │
  │  │ Predictive Lead  │  │ Orchestrator   │  │ Simulator   │  │
  │  │ Baseline Windows │  │ 10 Typed Tools │  │  Erlang-C   │  │
  │  │ Multi-Signal Lead│  │ Cited Evidence │  │ Donor Guard │  │
  │  └─────────┬────────┘  └───────┬────────┘  └──────┬──────┘  │
  │            │                   │                  │         │
  │  ┌─────────┴───────────────────┴──────────────────┴──────┐  │
  │  │        Incident Lifecycle & Human Approval Ledger     │  │
  │  │    Authenticated Sign-off  •  60m Cooldown Matrix     │  │
  │  └─────────────────────────────┬─────────────────────────┘  │
  └────────────────────────────────┼────────────────────────────┘
                                   │
  ┌────────────────────────────────┴────────────────────────────┐
  │         26 Authoritative Synthetic CSV Data Fixtures        │
  │     43,680 30-min Intervals  •  5 Queues  •  910 Days       │
  └─────────────────────────────────────────────────────────────┘
```

1. **Continuous Operations Intelligence Layer (COIL):**
   - Zero future information leakage in temporal replay (`timestamp < as_of`).
   - Intra-day velocity and multi-signal cross-queue correlation.
   - **30-minute early warning lead time** before observed SLA floor breaches.
2. **Google AI / Gemini Orchestrator:**
   - Official `google-genai` SDK integration.
   - **10 read-only typed analytical tools** (metrics, baselines, trends, capacity pressure, related signals, incident memory, policy search, forecasting, intervention simulation).
   - Structured hypothesis evaluation (`SUPPORTED`, `CONTRADICTED`, `UNKNOWN`) backed by exact cited evidence IDs.
   - Truthful fallback mode (`ai_mode: DETERMINISTIC_FALLBACK`) with zero fabricated hallucinations.
3. **Constrained Decision Simulator:**
   - Exact Erlang-C delay probability $C(c, A)$ and exponential queue service clearance.
   - Strict delay monotonicity guarantee ($\text{SLA}(c+1) \ge \text{SLA}(c)$).
   - **Donor-queue floor protection guardrails** preventing destabilization of donor operations.
4. **Human Approval State Machine & Notification Ledger:**
   - Mandatory authenticated human sign-off (`actor`, `role`, timestamp, notes).
   - Strict transition validation (rejects illegal jumps); idempotent approval requests.
   - Notification matrix routing with 60-minute deduplication cooldown window.

---

## 3. Project Structure

```
opsentia-v2/
├── backend/
│   ├── app.py                   # FastAPI application & API endpoints
│   ├── business_metrics.py      # Strict weighted SLA, AHT, abandon, occupancy, WAPE
│   ├── coil.py                  # Continuous Operations Intelligence Layer & early warning
│   ├── agent.py                 # Google AI / Gemini orchestrator & 10 read-only tools
│   ├── simulation.py            # Exact Erlang-C capacity model & donor guardrail
│   └── incidents.py             # Incident state machine & human approval ledger
├── data/
│   └── synthetic/               # 26 authoritative synthetic operational CSV fixtures
├── frontend/
│   └── app/                     # Approved 7-screen desktop UI
├── tests/
│   ├── test_metrics.py          # Metric calculations & stock-flow conservation tests
│   ├── test_coil.py             # Zero-leakage & early warning lead time tests
│   ├── test_agent.py            # Gemini tool execution & injection defense tests
│   ├── test_simulation.py       # Erlang-C capacity & monotonicity tests
│   ├── test_incidents_approvals.py # Incident lifecycle & human approval tests
│   └── test_visual_api.py       # UI bootstrap contract tests
├── scripts/
│   ├── preflight_data.py        # 43,680-row data reconciliation script
│   ├── browser_test_and_capture.py # Playwright multi-viewport automated QA
│   ├── record_demo_walkthrough.py  # Playwright automated 1080p demo video recorder
│   └── update_presentation.py   # PowerPoint deck updater with live screenshots
├── docs/
│   ├── BENCHMARKS.md            # Comprehensive benchmark & provenance evidence
│   ├── RELEASE_EVIDENCE.md      # Acceptance matrix across all release gates
│   ├── DEMO_VIDEO_3_MINUTES.md  # 180-second demonstration script
│   ├── screenshots/             # 25 authentic screenshots across 3 viewports
│   └── demo_video/              # 1080p walkthrough video recording (32.6 MB)
├── pitch/
│   ├── Opsentia_Official_Template_Final.pptx # Updated pitch presentation deck
│   └── Opsentia_Official_Template_Draft.pptx # Base presentation template
├── qa/
│   └── RELEASE_GATES.csv        # Gate acceptance matrix (RG-01 through RG-18)
├── Dockerfile                   # Cloud Run container with dynamic ${PORT:-8080}
├── requirements.txt             # Python dependencies
└── README.md                    # Project documentation
```

---

## 4. Getting Started

### Prerequisites
- Python 3.11+
- Chrome or Chromium (for Playwright browser verification)

### Installation
```bash
# Clone or navigate to the repository root
cd opsentia-v2

# Install dependencies
pip install -r requirements.txt
```

### Running Locally
```bash
# Start backend server (default Cloud Run port 8080, or port 8000)
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080
```
Open your browser to `http://127.0.0.1:8080` (or `http://127.0.0.1:8000` if port 8000 is unallocated) to access the full 7-screen interactive application.

---

## 5. Verification & Testing

### 1. Data Integrity Preflight
```bash
python scripts/preflight_data.py
```
*Reconciles all 26 synthetic CSV fixtures (43,680 records across 5 queues and 910 queue-days).*

### 2. Automated Regression Unit Tests
```bash
python -m pytest -q
```
*Executes all 30 automated test cases spanning business metrics, COIL, Gemini agent tools, Erlang-C simulations, and human approval state transitions. Result: **30 passed (100%)**.*

### 3. Multi-Viewport Browser QA & Screenshot Capture
```bash
python scripts/browser_test_and_capture.py
```
*Launches headless Chromium across 1366×768, 1440×900, and 1920×1080 viewports, tests interactive investigation and approval workflows, verifies 0 console errors, and captures 25 authentic screenshots in `docs/screenshots/`.*

### 4. Demo Walkthrough Video Recording
```bash
python scripts/record_demo_walkthrough.py
```
*Generates a high-definition 1920×1080 automated video walkthrough saved to `docs/demo_video/opsentia_demo_walkthrough.webm`.*

---

## 6. Deployment to Google Cloud Run

Opsentia is containerized and ready for immediate deployment to Google Cloud Run:

```bash
# Deploy to Google Cloud Run
gcloud run deploy opsentia \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="your-gemini-api-key"
```

The container automatically listens on the dynamic `${PORT:-8080}` provided by Cloud Run and serves the static frontend alongside the FastAPI REST API. The `/api/health` endpoint provides health-checking for Cloud Run load balancers.

---

## 7. Submission Artifacts & Evidence
- **Pitch Deck:** [`pitch/Opsentia_Official_Template_Final.pptx`](file:///c:/Users/Ai%20pc/Desktop/opsentia-v2/pitch/Opsentia_Official_Template_Final.pptx)
- **Demo Video:** [`docs/demo_video/opsentia_demo_walkthrough.webm`](file:///c:/Users/Ai%20pc/Desktop/opsentia-v2/docs/demo_video/opsentia_demo_walkthrough.webm)
- **Release Gates Acceptance Matrix:** [`qa/RELEASE_GATES.csv`](file:///c:/Users/Ai%20pc/Desktop/opsentia-v2/qa/RELEASE_GATES.csv)
- **Benchmark & Provenance Report:** [`docs/BENCHMARKS.md`](file:///c:/Users/Ai%20pc/Desktop/opsentia-v2/docs/BENCHMARKS.md)
- **Authentic Screenshots:** [`docs/screenshots/`](file:///c:/Users/Ai%20pc/Desktop/opsentia-v2/docs/screenshots/) (25 files across 3 viewports)
- **Release Verification Log:** [`docs/RELEASE_EVIDENCE.md`](file:///c:/Users/Ai%20pc/Desktop/opsentia-v2/docs/RELEASE_EVIDENCE.md)
