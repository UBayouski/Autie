"""Messaging channel adapters (docs/future-integrations.md §Messaging channels).

Each channel is a thin webhook adapter over the same agent service: it maps a
platform user id to an internal uid (so sessions, TTL, and rate limits apply
unchanged), enforces safety-layer parity, and re-renders output for the
platform. Adapters authenticate the platform (webhook secrets/signatures),
not the end user — they must never sit behind the Firebase auth dependency.
"""
