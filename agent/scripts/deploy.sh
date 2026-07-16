#!/bin/sh
# Build and deploy the agent to Cloud Run (source deploy via Cloud Build).
# Auth is ON in production: no AUTH_DISABLED here, ever.
set -e
cd "$(dirname "$0")/.."
. scripts/config.sh

# Gate the deploy on the unit tests (container build itself happens in Cloud Build).
.venv/Scripts/python.exe -m pytest tests/ -q

# Telegram channel secrets are mounted only once they exist — created by
# scripts/telegram-setup.sh. Until then the webhook route answers 404.
SECRETS="PLACES_API_KEY=autie-places-api-key:latest"
if gcloud secrets describe autie-telegram-bot-token --project "$PROJECT" >/dev/null 2>&1; then
    SECRETS="$SECRETS,TELEGRAM_BOT_TOKEN=autie-telegram-bot-token:latest"
    SECRETS="$SECRETS,TELEGRAM_WEBHOOK_SECRET=autie-telegram-webhook-secret:latest"
fi

gcloud run deploy "$SERVICE" \
    --source . \
    --project "$PROJECT" \
    --region "$REGION" \
    --allow-unauthenticated \
    --service-account "$SERVICE_ACCOUNT" \
    --min-instances 0 --cpu 1 --memory 512Mi --concurrency 20 --timeout 300 \
    --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,GEMINI_MODEL=$GEMINI_MODEL,SESSION_TTL_DAYS=30,RATE_LIMIT_PER_HOUR=60" \
    --set-secrets "$SECRETS" \
    --quiet

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format="value(status.url)"
