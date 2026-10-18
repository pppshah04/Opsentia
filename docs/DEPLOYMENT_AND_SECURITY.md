# Secure deployment and Cloud Run release plan
## Minimum deployment proof
Cloud Run hosts FastAPI and static frontend in **one service**. Required: publicly accessible or judge-accessible URL; health endpoint, seven pages, Gemini investigation (with configured Vertex AI/service identity), data loading and approval flow working on deployed instance. Do not treat `docker build` or local `/api/health` as verification of Cloud Run.

## Config
Use `.env.example` as names only. Recommended deployment: service account with minimum Vertex AI/Firestore permission, `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GEMINI_MODEL` from supported list, `STATE_BACKEND=firestore` if used. For local key use env injection only and do not commit. Do not expose keys in response, logs, frontend bundle, screenshots or Git archive.

## Infra and persistence
- Cloud Run filesystem ephemeral. Read packaged CSVs via image read-only. Mutable incident/approval/notification/trace state in Firestore if state must survive refresh/instances; if no time, explicitly run isolated demo-session memory store and do not promise durability.
- Permission: read-only tools for LLM, mutation APIs guarded by demo identity/CSRF or session token appropriate to public demo. Rate-limit expensive model and state mutations, max token spend, timeouts/retries.
- HTTP security: CORS only expected origins, input schemas, HTML escaping, resource limits, no arbitrary code or SQL execution.
- Retrieval prompt injection: synthetic policy text is untrusted evidence; no instruction following from documents.
- Privacy: no real customer/agent PII; only synthetic fixture data. Trace should store tool IDs and rounded/provenance summaries, never credentials.

## Build/run commands
```bash
python -m pip install -r requirements.txt
python scripts/preflight_data.py
python -m pytest -q
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8080
# container should listen on ${PORT:-8080}; make Dockerfile work under Cloud Run
# gcloud auth login; gcloud config set project PROJECT_ID
# gcloud services enable run.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com
# gcloud run deploy opsentia --source . --region REGION --allow-unauthenticated
```
Do not copy example GCP role flags or service account assumptions blindly; follow official Cloud Run docs and least privilege. Hosting may incur billing.

## Deployment verification
Record deployed service URL/time, screenshot of `/api/health` (app health != Gemini verified), 2 tool calls in a successful `/api/investigate` trace, persistent write/read proof if Firestore, 1366/1440/1920 browser check, environment/mode badges and request latency. Keep source repository public only after secret scan; code and synthetic data safe to share, screenshots of credentials never.

## Failure modes
If model cannot be configured, prominently label agent UNVERIFIED and do not claim judging compliance; resolve before submitting. If Firestore unavailable, use in-memory demo mode and mark persistence ephemeral; do not claim production-ready. If API deployment fails, do not submit a screenshot URL as working product.
