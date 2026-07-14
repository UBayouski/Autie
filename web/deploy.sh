#!/bin/sh
# Build the Angular app and deploy to Firebase Hosting.
# Hosting serves static files, so the local build IS required here -
# unlike agent/scripts/deploy.sh where Cloud Build builds the container.
set -e
cd "$(dirname "$0")"

npx ng build
npx firebase-tools deploy --only hosting --project autie-2
