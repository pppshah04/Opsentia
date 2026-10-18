# Cloud Run Deployment — after the app is actually implemented

Official references:
- https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-adk-service
- https://github.com/google/adk-docs/blob/main/docs/deploy/cloud-run.md

## Local
```
python -m pip install -r requirements.txt
python scripts/preflight_data.py
pytest -q
uvicorn backend.app:app --host 0.0.0.0 --port 8080
```
The starter API is a **read-only skeleton**, not an AI-powered application. Its `/api/health` intentionally reports `gemini_verified=false`. Do **not** publish its URL as the final working prototype.

## Cloud Run (only after real UI, Gemini, data and persistence are implemented)
1. Create GCP project and enable billing; choose region and set budget alerts.
2. Use Secret Manager / attached service account for credentials; do not include .env in image or GitHub.
3. Configure deployed ADK/Gemini with actual supported current model ID and runtime auth.
4. Configure Firestore (or explicitly labeled demo read-only mode); never rely on Cloud Run local SQLite as durable.
5. Build frontend (`npm ci && npm run build`) and mount static `dist/` in FastAPI or deploy frontend separately on Firebase Hosting if time permits.
6. Run `gcloud run deploy opsentia --source . --region REGION --project PROJECT --allow-unauthenticated` only after ensuring public exposure is safe and any writable endpoints require auth.
7. External smoke test `/`, `/api/health`, known replay incident, `/api/investigate`, one hypothetical intervention, and full browser flow.
8. Record actual Cloud Run URL and `X-Request-ID` trace. Save screenshots and CLI output under a private evidence folder.

## Failure handling
If Google auth or Gemini fails: display 'Gemini unavailable — deterministic analysis'; don't mark technical gate passed and don't silently use prerecorded AI content.
