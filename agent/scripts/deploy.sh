#!/bin/sh
# Build and deploy the agent to Cloud Run (source deploy via Cloud Build).
# Auth is ON in production: no AUTH_DISABLED here, ever.
set -e
cd "$(dirname "$0")/.."
. scripts/config.sh

gcloud run deploy "$SERVICE" \
    --source . \
    --project "$PROJECT" \
    --region "$REGION" \
    --allow-unauthenticated \
    --min-instances 0 --cpu 1 --memory 512Mi --concurrency 20 --timeout 300 \
    --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,GEMINI_MODEL=$GEMINI_MODEL" \
    --set-secrets "PLACES_API_KEY=autie-places-api-key:latest" \
    --quiet

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format="value(status.url)"
