#!/bin/sh
# Show recent Cloud Run logs for the agent service. Usage: ./logs.sh [limit]
set -e
. "$(dirname "$0")/config.sh"

gcloud run services logs read "$SERVICE" \
    --project "$PROJECT" --region "$REGION" --limit "${1:-50}"
