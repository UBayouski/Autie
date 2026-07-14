# Autie agent service

Python + Google ADK chat backend (FastAPI, SSE streaming) for Autie 2.0.
Architecture: [../docs/architecture.md](../docs/architecture.md).

## Local development

Prereqs: Python 3.12+, a GCP project with the Vertex AI API enabled, and
`gcloud auth application-default login` run once.

```sh
cd agent
python -m venv .venv
.venv\Scripts\activate          # Windows (or: source .venv/bin/activate)
pip install -e .[dev]
copy .env.example .env          # then set GOOGLE_CLOUD_PROJECT
uvicorn app.main:app --reload --port 8080
```

Smoke test:

```sh
curl http://localhost:8080/health
curl -N -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Hi, what can you help with?\"}"
```

The response is an SSE stream of JSON events:

| type | payload | meaning |
|---|---|---|
| `session` | `session_id` | pass back in the next request to continue the conversation |
| `text_delta` | `text` | streamed token chunk |
| `text_final` | `text` | complete final message (redundant if deltas were consumed) |
| `done` | — | turn finished |
| `error` | `message` | user-safe error text |

With `AUTH_DISABLED=true` unset (i.e. production behavior), requests need
`Authorization: Bearer <Firebase ID token>`.

## Tools

- `find_local_services(what, where)` — Places API (New) text search, USA-biased,
  operational places only. The agent asks for missing what/where before calling.
  Needs `PLACES_API_KEY` (a key restricted to `places.googleapis.com`): from the
  `autie-places-api-key` secret on Cloud Run, from `.env` locally.
- `search_knowledge_base(question)` — custom RAG on Firestore vector search
  (`rag_chunks`, 768-dim `gemini-embedding-001`, COSINE, top-6). Answers are
  cited inline. Guardrails: `../docs/rag-constraints.md`. Corpus + pipeline:
  `ingestion/`; retrieval evals: `RUN_RAG_EVALS=1 pytest tests/test_rag_evals.py`.

  Ingestion is manual and independent of deploys — Cloud Run only reads
  `rag_chunks`, so shipping the agent never rebuilds the index. Rebuild after
  editing `ingestion/corpus.json`:

  ```
  python -m ingestion.ingest --dry-run   # fetch + chunk only, no writes, no cost
  python -m ingestion.ingest             # upsert every chunk in place
  python -m ingestion.ingest --prune     # ...then delete chunks dropped from the manifest
  ```

  `--prune` sweeps after a clean ingest rather than wiping first, so a failed
  run can't leave the index empty; it self-skips if any source failed to fetch.
  Corpus mix is intentionally ~70% autism / ~30% other neurodevelopmental
  conditions. PMC sources are fetched via the NCBI E-utilities API — the
  article pages serve a reCAPTCHA to scripts, which scrapes as junk text.
- `get_crisis_resources()` — deterministic USA crisis directory (988 etc.),
  served verbatim; also emitted by the safety pre-check in `app/safety/`.

## Helper scripts (Git Bash / any POSIX shell)

| script | what it does |
|---|---|
| `scripts/dev.sh` | run locally with auto-reload (needs `.env` + gcloud ADC) |
| `scripts/deploy.sh` | build + deploy to Cloud Run, prints the service URL |
| `scripts/logs.sh [n]` | read the last *n* (default 50) Cloud Run log lines |
| `scripts/chat.sh "msg" [session_id]` | chat from the terminal; `BASE_URL=`/`TOKEN=` env vars target the deployed, authenticated service |

Defaults (project `autie-2`, region `us-central1`, service `autie-agent`) live in
`scripts/config.sh` and can be overridden via environment variables.

## Deploy to Cloud Run

```sh
gcloud run deploy autie-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 0 --cpu 1 --memory 512Mi --concurrency 20 --timeout 300 \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_LOCATION=us-central1
```

(`--allow-unauthenticated` is required because auth happens in-app via Firebase ID
tokens; Firebase Hosting rewrites `/api/**` to this service.)

## Tests

```sh
pytest
```
