#!/bin/sh
# Shared config for agent scripts. Override via environment, e.g. REGION=us-east1 ./deploy.sh
: "${PROJECT:=autie-2}"
: "${REGION:=us-central1}"
: "${SERVICE:=autie-agent}"
: "${GEMINI_MODEL:=gemini-2.5-flash}"
: "${SERVICE_ACCOUNT:=autie-agent@autie-2.iam.gserviceaccount.com}"
