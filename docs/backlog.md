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

- [ ] **Session TTL / retention policy** — sessions in the `adk` collection live
  forever today. Architecture §5 calls for auto-delete after N days unless the
  user opts into history. Cheapest: Firestore TTL policy on a `expire_at` field
  set by FirestoreSessionService. Also needed: a delete-my-data path.
- [ ] **Per-user rate limiting** — anonymous sign-up is free to abuse; cap
  requests/user/hour in the agent service (Firestore counter or in-memory +
  uid) before sharing the URL widely.
- [ ] **Crisis detector v2** — current detection is keyword/regex (deliberately
  false-positive-friendly). Consider a small classifier pass or LLM-based
  screening as a second tier; keep the deterministic card guarantee.
- [ ] **Budget alert** on the autie-2 GCP project (architecture §6 promised it;
  not yet configured).
- [ ] **Least-privilege service account** — Cloud Run runs as the default
  compute SA with roles/editor. Create a dedicated SA with only
  aiplatform.user, datastore.user, secretAccessor.

## Known issues / bugs

- [x] **Web: session lost on page reload** — fixed 2026-07-14: session id in
  localStorage, history restored via new `GET /api/sessions/{id}` endpoint,
  plus a "New chat" reset button. Revisit storage duration with the retention
  policy.
- [x] **Web: multi-part model turns can overwrite text** — fixed 2026-07-14:
  each final segment gets its own bubble (`lastSegmentDone` flag in
  ChatService); matches how restore renders history. Note: the multi-final
  case is model-dependent and wasn't reproducible on demand — logic-reviewed
  and deployed; confirm from real usage.
- [ ] **Web: composer doesn't auto-grow** — `rows=1` textarea with a CSS
  max-height but no height adjustment on input; long messages scroll inside a
  one-line box.
- [ ] **Agent: `list_sessions` across users needs a composite index** — the
  collection-group query in FirestoreSessionService filters on `app_name`
  without its index. Unused code path today; create the index or drop the
  cross-user variant when first needed.
- [ ] **Agent: concurrent requests on one session can interleave events** — no
  locking in FirestoreSessionService; two simultaneous sends on the same
  session id may interleave history. Low risk single-user, revisit with rate
  limiting.
- [ ] **Ingestion: Windows console mangles non-ASCII in logs** (cp1252) —
  cosmetic; set `PYTHONIOENCODING=utf-8` or log ASCII only.
- [ ] **Ingestion: 1st level domain is re-written** —
  for some reason 1st level domain in citation is sometimes changed 
  from original to something else. 
  Example: 
  https://www.cdc.gov/autism/signs-symptoms/index.html becomes
  https://www.cdc.com/autism/signs-symptoms/index.html

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
- [ ] Tool ideas beyond Places: see [future-integrations.md](future-integrations.md).

## Deliberately deferred decisions (with triggers)

- **Multi-agent split** — single root agent until a domain owns several tools;
  then AgentTool-wrapped specialist (architecture.md §Agent decomposition).
- **google-maps-places SDK + ADC auth** — when a second Maps surface is needed
  (note in app/tools/places.py).
- **RAG storage revisit** — only if corpus approaches ~50k chunks
  (docs/rag-constraints.md §4).
- **Vertex AI Agent Engine** — not planned; self-managed Cloud Run chosen.
