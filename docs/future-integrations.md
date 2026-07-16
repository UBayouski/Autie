# Autie — Future Tool & Integration Ideas

Backlog of agent tools/integrations beyond the initial Google Places implementation.
Each of these fits the agentic architecture as a new ADK tool (or small tool group) —
the agent validates required inputs conversationally before calling, same pattern as Places.

## Location-based (extends the Places tool)

- **Sensory-friendly venue finder** — Places results enriched by having the LLM scan
  reviews/editorial summaries for sensory cues (quiet hours, dim lighting, crowd levels).
  No new API needed; a prompt-level enhancement over Place Details.
- **Sensory-friendly event listings** — sensory-friendly movie screenings (AMC runs a
  recurring program), museum quiet hours, library sensory storytimes. Sources: Eventbrite
  API, local library/museum feeds.
- **Provider directories beyond Google Maps** — ABA/OT/SLP therapist registries
  (e.g., BACB certificant registry for behavior analysts, ASHA ProFind for SLPs/audiologists).
  Higher-quality results than generic Places category search.

## Navigation & advocacy (USA-focused)

- **IEP / special-education helper** — RAG corpus extension: IDEA law summaries,
  state-specific parent guides, Wrightslaw-style plain-language explainers. Tool angle:
  lookup of state Parent Training and Information Centers (every US state has one, federally funded).
- **Insurance / Medicaid waiver navigation** — state-by-state autism insurance mandate
  and Medicaid HCBS waiver lookup. Data is mostly static tables → could live in Firestore
  as a structured tool rather than RAG.
- **SSI / benefits screener pointers** — not eligibility advice, but "here's what SSI is
  and where to apply" with official links.

## Crisis & support (safety-adjacent, high value)

- **Crisis resources tool** — deterministic (not LLM-generated) directory: 988 Suicide &
  Crisis Lifeline, Crisis Text Line, Autism Society helpline (800-328-8476). Invoked by the
  safety layer, not only by user request.
- **Caregiver respite finder** — ARCH National Respite Locator; state respite programs.
- **Support group finder** — Autism Society local affiliates, parent support groups
  (combinable with Places).

## Content generation (LLM-native, no external API)

- **Social story generator** — parent describes an upcoming situation (dentist visit,
  first flight), agent drafts a simple social story. Optionally with images later.
- **Visual schedule builder** — structured daily-routine output the Angular UI renders
  as printable cards.
- **"Explain this report" mode** — parent pastes text from an evaluation/IEP document,
  agent explains jargon in plain language. Requires clear privacy handling (don't persist,
  say so explicitly).

## Communication & reminders

- **Email/summary export** — send the conversation's action items or found services list
  to the user's email (they're logged in via Firebase Auth anyway).
- **Appointment prep checklists** — generated checklist for first visits to a found
  provider (questions to ask, documents to bring).

## Platform reach (later)

- **Spanish language support** — biggest underserved caregiver population in the USA;
  mostly a prompt/RAG-corpus effort, worth planning the corpus metadata for from the start.

### Messaging channel integrations (added 2026-07-15)

Meet caregivers where they already are instead of requiring a web visit. The agent
service is channel-agnostic (FastAPI + Runner); each channel is a thin webhook adapter
that maps platform user id → internal uid and re-renders output for that platform.

Candidate channels, roughly by fit:

- **WhatsApp** — biggest US caregiver reach, especially Spanish-speaking families.
  WhatsApp Business Platform (Meta Cloud API directly, or via Twilio — Twilio also
  gives SMS through the same adapter). Needs Meta Business verification; replies are
  restricted to a 24-hour service window after the user's last message (fine for a
  user-initiated Q&A bot); service replies free, business-initiated templates paid.
- **SMS (Twilio)** — not asked-for but worth bundling with the WhatsApp adapter:
  reaches low-income caregivers without smartphones/data; plain-text only.
- **Facebook Messenger** — same Meta app/business review pipeline as WhatsApp; needs
  a Facebook Page; also enforces a 24-hour messaging window. Free.
- **Telegram** — low US caregiver penetration, so not a reach play — but the best
  **capability-proof channel** (decided 2026-07-15): free Bot API, token from
  BotFather in minutes, no business verification or review, no send costs, good
  formatting (prefer HTML parse mode over MarkdownV2 — escaping rules are painful).
  Building it first validates the whole adapter pattern (webhook, async reply,
  id→uid mapping, crisis-card parity, per-channel rendering) before committing to
  Meta's weeks-long verification pipeline. What it does NOT validate: WhatsApp's
  24-hour window/template mechanics, and US demand.
- **Google Chat (Workspace)** — different audience: educators/school staff on
  Workspace for Education, not parents. Ship via Workspace Marketplace app. Park it
  until the educator persona is a focus.
- **Discord** — later maybe; active autistic-adult and parent communities exist, but a
  shared-server bot raises group-chat privacy questions the 1:1 channels don't have.

Cross-cutting considerations (apply to every channel):

- **No streaming** — messengers are message-in/message-out; buffer the full reply.
  Webhooks must be ACKed fast (Meta ~seconds) → ack immediately, process async, push
  the reply via the platform's send API (Cloud Tasks or background task).
- **Identity** — no Firebase token; adapter maps platform id (phone / PSID / chat id)
  to an internal uid so sessions, 30-day TTL, and the 60/hr rate limit apply unchanged.
  Store the mapping hashed where the platform id is a phone number.
- **Safety layer parity** — the deterministic crisis card must render per channel
  (plain-text template, still verbatim, still before the model reply). Test per channel;
  this is non-negotiable before any channel launches.
- **Privacy** — conversations transit Meta/Telegram servers and persist on the user's
  device/platform account; our TTL only governs our copy. Needs a per-channel
  disclosure line and a privacy-policy update; health-adjacent content on third-party
  rails is a real posture change from the self-hosted web app.
- **Formatting** — markdown support differs wildly (Telegram MarkdownV2, WhatsApp
  minimal, SMS none); the Sources footer and Places links need per-channel renderers.
- **Ops** — Meta app review + business verification has weeks of lead time; each
  channel widens the abuse/moderation surface. Trigger: after the public web launch
  proves demand (feedback signal), not before.

Sequencing (updated 2026-07-15): **Telegram first** as the capability demo — it
proves the adapter architecture with zero platform gatekeeping and can ship any
time. **Twilio (WhatsApp + SMS)** stays the first *reach* channel, triggered by
post-launch demand; start Meta business verification early since it has weeks of
lead time. Crisis-card parity is required before any bot is public, including a
demo Telegram bot.

## Prioritization note

Suggested order after Places ships: crisis resources tool (small, high value, needed by
the safety layer anyway) → social story generator (pure LLM, no integration cost, very
shareable) → IEP/state resource lookup (static data, big USA-specific value).
