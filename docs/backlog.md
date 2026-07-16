# Autie 2.0 — Status & Backlog

Living document. Update when items ship or new work is queued.
Last updated: 2026-07-14.

## Migration plan status (architecture.md §Migration order)

| # | Step | Status |
|---|---|---|
| 1 | Agent service scaffold (ADK + FastAPI + SSE + auth) on Cloud Run | ✅ done |
| 2 | Places tool (Places API New, slot-filling via agent) | ✅ done |
| 3 | Angular chat UI (Angular 22, streaming, anonymous auth) on Hosting | ✅ done |
| 4 | Safety layer (crisis pre-check + verbatim resources + safety settings + post-check) | ✅ done |
| 5 | RAG knowledge base (Firestore vector search, 48 chunks, cited answers, 12 evals) | ✅ done |
| 6 | Evals growth + conversation-level evals + autie.chat DNS cutover; archive old stack | ⬜ open |

Live: https://autie-2.web.app (web) → https://autie-agent-655618767802.us-central1.run.app (agent)

## Hardening backlog (before public announcement)

- [x] **Session TTL / retention policy** — done 2026-07-14: 30-day rolling TTL.
  FirestoreSessionService writes `expire_at` on session docs (refreshed per
  event) and event docs (fixed at write time); Firestore TTL policies enabled
  on the `sessions`, `events`, and `rate_limits` collection groups; existing
  docs backfilled (38 sessions, 259 events). `SESSION_TTL_DAYS` env (0
  disables). Delete-my-data: `DELETE /api/sessions/{id}` and `DELETE /api/me`.
  Note: TTL deletion lags up to ~24h; conversations active longer than the TTL
  shed their oldest events first. Web UI for deletion not wired yet.
- [x] **Per-user rate limiting** — done 2026-07-14: 60 requests/uid/clock-hour
  (`RATE_LIMIT_PER_HOUR` env, 0 disables), 429 before streaming. Firestore
  counter (`rate_limits/{uid}:{hour}`) so limits survive scale-to-zero and are
  shared across instances; fails OPEN so a Firestore hiccup can't take chat
  down; counter docs self-clean via the same TTL mechanism.
- [ ] **Crisis detector v2** — current detection is keyword/regex (deliberately
  false-positive-friendly). Consider a small classifier pass or LLM-based
  screening as a second tier; keep the deterministic card guarantee.
  (Deliberately left out of the 2026-07-14 hardening pass — needs its own
  design + eval work.)
- [x] **Budget alert** — done 2026-07-14: $25/month budget on the billing
  account scoped to autie-2, alerts at 50/90/100% to billing admins.
- [x] **Least-privilege service account** — done 2026-07-14: Cloud Run now
  runs as `autie-agent@autie-2.iam.gserviceaccount.com` with only
  roles/aiplatform.user + roles/datastore.user (project) and
  secretmanager.secretAccessor on the `autie-places-api-key` secret only.
  Set via `--service-account` in deploy.sh. Firebase token verification needs
  no IAM role (public certs). Default compute SA no longer used by the
  service (its roles/editor grant can be trimmed separately if desired).

## Known issues / bugs

- [ ] **Retrieval evals: 2 cases drifted after corpus expansion** — found
  2026-07-15 while running the opt-in evals (`RUN_RAG_EVALS=1`): "What causes
  autism spectrum disorder?" and the speech-therapy question no longer surface
  nichd.nih.gov in top results (outranked by CDC/PMC/MedlinePlus — reasonable
  sources, so likely the eval expectations are stale rather than retrieval
  being wrong). Review expectations vs. ranking as part of the "Corpus growth /
  evals growth" item; unrelated to the agent-persona change made the same day
  (retrieval never sees the instruction).

- [x] **Web: session lost on page reload** — fixed 2026-07-14: session id in
  localStorage, history restored via new `GET /api/sessions/{id}` endpoint,
  plus a "New chat" reset button. Storage duration now bounded by the 30-day
  session TTL (see hardening); a reload after expiry starts a fresh session.
- [x] **Web: multi-part model turns can overwrite text** — fixed 2026-07-14:
  each final segment gets its own bubble (`lastSegmentDone` flag in
  ChatService); matches how restore renders history. Note: the multi-final
  case is model-dependent and wasn't reproducible on demand — logic-reviewed
  and deployed; confirm from real usage.
- [x] **Web: composer doesn't auto-grow** — fixed 2026-07-15: grows with input
  up to the CSS max-height (verified 46→128px, capped), resets on send.
- [x] **Agent: `list_sessions` across users needs a composite index** — fixed
  2026-07-15: the cross-user path now raises NotImplementedError with the fix
  described, instead of failing confusingly at query time.
- [x] **Agent: concurrent requests on one session can interleave events** —
  mitigated 2026-07-15: per-session asyncio lock serializes sends within an
  instance (covers same-tab/two-tab cases at current concurrency). Residual:
  cross-instance races; revisit if instances > 1 becomes common.
- [x] **Ingestion: Windows console mangles non-ASCII in logs** — fixed
  2026-07-15: stdout reconfigured to UTF-8 in ingest.py.
- [x] **Citations: domain sometimes re-written** (cdc.gov → cdc.com) — fixed
  2026-07-15 structurally: the model now cites by source NAME only and never
  writes URLs; the backend appends a "Sources" footer built verbatim from the
  tool payload (main.py collects source_urls from function responses). The
  footer lists all sources retrieved for the turn ("sources consulted").
  Same pattern to apply to Places links with structured service cards.

Bug policy: quick fixes land immediately; anything deferred gets a line here
(or a GitHub issue once the project has outside contributors — at that point
migrate this section to Issues).

## Product backlog

- [ ] **Visual design pass** — apply the finished autie-2 design to `web/` as a
  token/template pass (tokens live in `web/src/styles.css`).
- [ ] **Conversation history UI** — list past sessions (data already persists
  per uid); pairs with the retention/opt-in decision.
- [ ] **Account linking** — optional "sign in with Google to keep your history
  across devices" (Firebase anonymous → permanent link; same uid).
- [ ] **Structured service cards** — backend emits typed SSE parts for Places
  results; web renders cards instead of markdown lists.
- [ ] **Corpus growth** — more sources (state education agencies, IDEA/IEP
  guides, Autism Society materials — license-check each), grow eval set
  alongside (evals/retrieval_eval.json).
- [ ] **Feedback signal** — thumbs up/down per answer, stored with session id;
  becomes the seed for conversation-level evals.
- [ ] **Places caching → curated services directory** — don't build a raw
  response cache: Google ToS caps caching most Places content (~30 days;
  only place IDs may be stored indefinitely), and stale phone/status data is
  high-harm for this audience. Instead: Firestore directory keyed by place_id
  with our own metadata (autism-relevance tags, feedback, verified flags),
  Google-sourced fields refreshed via Place Details within the allowed window;
  short-TTL query cache on top if latency/cost ever warrants it.
- [ ] **Messenger channel integrations** — WhatsApp, SMS, FB Messenger, Telegram,
  Google Chat as thin webhook adapters over the same agent service. Details,
  per-platform fit, and cross-cutting concerns (no streaming, identity mapping,
  crisis-card parity, privacy posture) in
  [future-integrations.md §Messaging channels](future-integrations.md).
  First move: **Telegram** — not for US reach, but as the capability proof for
  the adapter architecture (no Meta verification/review, ships any time; crisis-card
  parity still required before the bot is public). Twilio (WhatsApp + SMS) remains
  the first reach channel; trigger: post-launch demand signal.
  - [x] Telegram adapter built 2026-07-15 (`agent/app/channels/telegram.py`,
    tests in `tests/test_telegram.py`): `/webhooks/telegram` with webhook-secret
    auth, uid `tg-<chat_id>` (TTL + rate limit apply unchanged), verbatim crisis
    card before the model reply, HTML rendering with plain-text fallback,
    4096-char splitting, `/start` privacy disclosure, `/forget` delete-my-data,
    update_id dedupe, 1:1 chats only. Enable with `scripts/telegram-setup.sh`
    (BotFather token → Secret Manager → deploy → setWebhook); until then the
    route answers 404. Processes in-request (no Cloud Tasks hop yet — upgrade
    path if turn latency exceeds Telegram's webhook patience).
- [ ] Tool ideas beyond Places: see [future-integrations.md](future-integrations.md).

## Deliberately deferred decisions (with triggers)

- **Multi-agent split** — single root agent until a domain owns several tools;
  then AgentTool-wrapped specialist (architecture.md §Agent decomposition).
- **google-maps-places SDK + ADC auth** — when a second Maps surface is needed
  (note in app/tools/places.py).
- **RAG storage revisit** — only if corpus approaches ~50k chunks
  (docs/rag-constraints.md §4).
- **Google Search grounding** — not used; RAG citations + Places cover today's
  needs, and Gemini's built-in google_search doesn't mix freely with custom
  function tools. Trigger: freshness features (events, news) — build as a
  search specialist behind AgentTool at that point.
- **Vertex AI Agent Engine** — not planned; self-managed Cloud Run chosen.
