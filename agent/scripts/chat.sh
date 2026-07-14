#!/bin/sh
# Chat with the agent from the terminal (SSE stream).
#
# Usage:
#   ./chat.sh "your message"                          # local server (localhost:8080)
#   ./chat.sh "your message" <session_id>             # continue a conversation
#   BASE_URL=https://... ./chat.sh "your message"     # deployed service
#   TOKEN=<firebase-id-token> BASE_URL=... ./chat.sh "msg"   # authenticated
set -e

MESSAGE="${1:?usage: chat.sh \"message\" [session_id]}"
SESSION="$2"
: "${BASE_URL:=http://localhost:8080}"

if [ -n "$SESSION" ]; then
    BODY=$(printf '{"message": %s, "session_id": "%s"}' "$(printf '%s' "$MESSAGE" | python -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" "$SESSION")
else
    BODY=$(printf '{"message": %s}' "$(printf '%s' "$MESSAGE" | python -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")
fi

if [ -n "$TOKEN" ]; then
    curl -s -N -X POST "$BASE_URL/api/chat" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "$BODY"
else
    curl -s -N -X POST "$BASE_URL/api/chat" -H "Content-Type: application/json" -d "$BODY"
fi
