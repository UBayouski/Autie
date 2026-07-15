#!/bin/sh
# One-time Telegram channel setup: stores the bot token in Secret Manager,
# generates the webhook secret, grants the service account access, deploys,
# and registers the webhook with Telegram.
#
# Prerequisite: create a bot with @BotFather (/newbot) and grab its token.
# Usage: TELEGRAM_BOT_TOKEN=<token> ./telegram-setup.sh
#
# Safe to re-run (e.g. after rotating the bot token via BotFather): secrets
# get a new version, the webhook secret is reused, and setWebhook is
# idempotent.
set -e
cd "$(dirname "$0")/.."
. scripts/config.sh

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Set TELEGRAM_BOT_TOKEN to the token from @BotFather." >&2
    exit 1
fi

ensure_secret() { # name value
    if gcloud secrets describe "$1" --project "$PROJECT" >/dev/null 2>&1; then
        printf '%s' "$2" | gcloud secrets versions add "$1" --project "$PROJECT" --data-file=- >/dev/null
    else
        printf '%s' "$2" | gcloud secrets create "$1" --project "$PROJECT" --data-file=- >/dev/null
    fi
    gcloud secrets add-iam-policy-binding "$1" --project "$PROJECT" \
        --member "serviceAccount:$SERVICE_ACCOUNT" \
        --role roles/secretmanager.secretAccessor >/dev/null
}

ensure_secret autie-telegram-bot-token "$TELEGRAM_BOT_TOKEN"

# Reuse the existing webhook secret if there is one — Cloud Run resolves
# :latest at instance start, so minting a new value on every run would desync
# running instances from what Telegram sends.
if ! WEBHOOK_SECRET=$(gcloud secrets versions access latest \
        --secret autie-telegram-webhook-secret --project "$PROJECT" 2>/dev/null); then
    WEBHOOK_SECRET=$(openssl rand -hex 32)
    ensure_secret autie-telegram-webhook-secret "$WEBHOOK_SECRET"
fi
echo "Secrets ready."

# Deploy so the service picks the secrets up (deploy.sh mounts them once they exist).
scripts/deploy.sh
SERVICE_URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format="value(status.url)")

echo "Registering webhook at $SERVICE_URL/webhooks/telegram ..."
curl -sS "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
    -d "url=$SERVICE_URL/webhooks/telegram" \
    -d "secret_token=$WEBHOOK_SECRET" \
    -d 'allowed_updates=["message"]' \
    -d "drop_pending_updates=true"
echo
curl -sS "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
echo
