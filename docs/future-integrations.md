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
- **SMS/WhatsApp channel** — Twilio in front of the same Cloud Run agent endpoint;
  reaches caregivers who won't install/visit an app.

## Prioritization note

Suggested order after Places ships: crisis resources tool (small, high value, needed by
the safety layer anyway) → social story generator (pure LLM, no integration cost, very
shareable) → IEP/state resource lookup (static data, big USA-specific value).
