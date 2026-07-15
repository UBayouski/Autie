# Employment Support — Design

Two phases. Phase 1 (a curated referral directory) is built. Phase 2 (aggregating
live openings) is designed but deliberately not started — see "Why Phase 1 first".

## Principles

These bind both phases. They are the reason the design looks the way it does.

### 1. Never infer which jobs "suit" a condition

Nothing in this system — model, filter, or schema — may map a condition to a
kind of work. An LLM asked "is this job good for an autistic person?" reproduces
the stereotype pipeline in its training data (autism → QA and data entry, ADHD →
sales, dyslexia → not writing). That is wrong at the individual level, it steers
people toward a narrower and lower-paid band of work than they would otherwise
reach, and coming from a support assistant the person already trusts it carries
authority a listicle does not.

We surface **employer-declared** signals only: "this employer runs an Autism at
Work program", "this posting states accommodations are available". Employer
claims are checkable, attributable, and do not tell anyone what they are capable
of. We are here to support diversity, not to sort people into boxes.

Concretely: no condition field on a job record, no condition→role mapping, no
"recommended for you" ranking by diagnosis.

### 2. Don't ask users for their diagnosis

Matching on "request details" must mean role, location, and work arrangement —
never a disclosed condition. A stated diagnosis is health data with real handling
obligations, and we have no use for it that principle 1 permits.

Related: surfacing "autism-friendly employers" nudges people toward disclosing a
diagnosis to an employer. Disclosure is a fraught, personal, legally loaded
decision (ADA accommodations require it; it also invites discrimination). Autie
presents options and never pushes toward disclosure.

### 3. Sanctioned sources only

No scraping job boards. LinkedIn/Indeed/Glassdoor prohibit it in ToS and block
it; postings are the employer's copyrighted text. Use employers' own ATS
endpoints (Greenhouse, Lever, Ashby, Workable) and official government APIs.

This is the `ingestion/` lesson: a blocked scrape returns HTTP 200 with a
CAPTCHA page and poisons the store silently.

### 4. Refer, don't replace

Where an organisation already does this well, point at them. Hire Autism (OAR)
offers free 1:1 resume and interview mentoring from human volunteers — Autie
cannot, and for someone trying to get hired that is worth more than a list of
links. Scraping a nonprofit's curated work to build a thinner competing surface
is both bad practice and bad manners.

### 5. USA only, for now

Consistent with `find_local_services` (USA-biased) and the crisis directory
(988). Every Phase 1 resource is a US federal program or US nonprofit.

## Phase 1 — curated referral directory (BUILT)

`get_employment_resources()` in `app/tools/employment.py`, following the
`get_crisis_resources` pattern: a hand-verified constant, served verbatim, never
paraphrased by the model. No network call, no store, no staleness, no cost.

Six resources, each verified reachable with its contact details checked against
the source before landing:

| Resource | Why it's here |
|---|---|
| Job Accommodation Network | DOL/ODEP-funded, free, confidential accommodation guidance |
| Ticket to Work (SSA) | work without losing SSDI/SSI — free, badly underused |
| State Vocational Rehabilitation | free federal entitlement, all 78 agencies, most people don't know it exists |
| CareerOneStop / American Job Centers | DOL, free, in-person, 160+ languages |
| Hire Autism (OAR) | autism-specific board **plus free human mentoring** |
| Autism Job Board | autism/neurodiversity board (Autism Foundation of Oklahoma, ACL-supported) |
| EARN neurodiversity hiring directory | DOL-funded list of employers running programs — the list we defer to |

### Named employers are a separate section

`employer_programs` (currently Microsoft and SAP) is deliberately kept out of
`resources`. Two reasons:

- **Everything in `resources` is a free service open to anyone. A company is
  not.** Mixing them makes Autie look like it endorses an employer.
- **A list of employers curated by us implies completeness we can't deliver.**
  Naming one company invites "why not SAP, EY, JPMorgan?"; naming five invites
  the same question about the sixth. The fix is EARN: a DOL-funded directory of
  these programs already exists and is maintained by someone whose job it is.
  We point at it, and name a couple of examples with an explicit
  not-a-recommendation caveat.

Describe what a program's **process** offers (an adjusted interview, a general
application). Never reproduce the employer's marketing about what neurodivergent
people are supposedly good at — "innovative thinking", "attention to detail" — 
that is principle 1's stereotype trap in a friendlier register, and it is
enforced by a test.

Maintenance: links rot. Re-verify periodically; a 404 on a program page is the
best available signal that a program quietly ended.

Verification strength differs slightly and is worth knowing: JAN, Ticket to
Work, RSA, CareerOneStop, Autism Job Board, EARN and Microsoft had their content
and contact details read directly. SAP's careers page is client-rendered, so the
URL was confirmed to resolve and the program independently corroborated via
EARN, but the page text could not be machine-read.

Excluded on purpose: the Neurodiversity Employment Network (DNS would not
resolve at build time — an unverifiable entry in a directory people act on is
worse than an absent one). Autism Speaks employment pages are omitted given the
organisation's contested standing with autistic self-advocates; this is a
community-trust call, revisit deliberately if at all.

### Evals

`RUN_EMPLOYMENT_EVALS=1 pytest tests/test_employment_evals.py -v` — nine cases in
`evals/employment_eval.json`, ~2 minutes. Run before accepting a model upgrade:
principle 1 is enforced by the instruction, and instructions are exactly what
drift when the model changes underneath them.

The cases split two ways, and the split is the point:

- **Discrete facts → mechanical.** Did the tool fire (and not fire on unrelated
  questions), is JAN's phone number intact, did it invent an SSDI dollar figure.
  Stable.
- **Stance → LLM judge.** Substring matching was tried first and was flaky: two
  equally correct refusals came back as "there isn't really one type of job" and
  "there's no single type of job"; a needle list tuned to the first failed the
  second. Correct answers have unbounded phrasings, so enumerating them is a
  losing game.

The judge defaults to a *different* model than the agent (`EVAL_JUDGE_MODEL`,
`gemini-2.5-pro`) because a same-model judge is likelier to share the blind spot
it exists to catch. Its criteria are narrow and behavioural ("does it recommend a
job because of the diagnosis?") rather than "is this good?" — vague criteria are
where judges become unreliable. It was calibrated against known-bad replies
before being trusted, and it caught the subtle one ("many autistic individuals
excel at this, you'd be great at software testing") that the substring canary let
through.

**Known accepted behaviour:** on the positive-stereotype prompt, Autie today
opens by affirming that many autistic people do work in these fields and *then*
redirects to the individual. That was judged acceptable — it never recommends the
job, and the claim isn't false — so the criterion permits the preamble and
targets only capitulation. This was a deliberate call: the alternative was more
instruction, which costs adherence budget on a small model and risked
overcorrecting onto legitimate factual questions. If you later disagree, tighten
the criterion in the JSON rather than growing `INSTRUCTION`.

## Phase 2 — live openings (DESIGNED, NOT BUILT)

Aggregate current openings at employers with a declared neurodiversity or
disability-inclusion commitment, queryable conversationally. The thing the
directories don't do.

```
jobs/employers.json      manifest, git-reviewed (see "approval" below)
  -> scheduled Cloud Run job, pulls each employer's ATS endpoint
  -> Firestore `job_postings`, active/expired swept like ingestion --prune
  -> find_jobs tool: structured query (location, remote, category)
```

**Not RAG.** This is structured filtering, not semantic search. Do not embed job
descriptions; a composite index on `(active, remote, category)` is the whole
retrieval story. `find_jobs` sits alongside `find_local_services` as a tool — a
sub-agent adds routing complexity for nothing.

### Approval is employer-level, not job-level

Put approval where the information advantage is. You can answer "is SAP's Autism
at Work program real, current, and honestly described?" — that is verifiable
research, done once, true for a year. You cannot answer "is SAP req #4432 a good
posting?" — you hold no information the feed doesn't. Job-level review therefore
decays into rubber-stamping within weeks: a click that feels like safety and
provides none.

More precisely: **job-level review is the right control for untrusted sources;
employer-level is right for trusted ones.** Principle 3 (pull from the
employer's own ATS) already made the source trusted, so job-level review
mitigates a risk the sourcing decision removed.

| | Employer-level | Job-level |
|---|---|---|
| Volume | ~50–150 once, then rare additions | unbounded, forever |
| Latency | none — postings flow live | days, against data that dies in days |
| Mechanism | `employers.json` PR, like `corpus.json` | admin UI to build and maintain |
| Revocation | drop employer, sweep their jobs | per posting |
| Skip a week | nothing happens | feature silently stalls |

The trade: a weak posting from a good employer gets through. Buy that back with
**machine** checks, not human ones — drop postings past a max age, missing
required fields, or flagged (pay-to-apply and similar) — plus a report-listing
path and annual employer re-review.

### Known open questions

- **Volume may be small.** Formal programs are real but modest: OAR's 2022
  figures were 206 job seekers mentored, 41 placed. Pulling whole ATS feeds from
  committed employers gives volume but a weaker claim (not every req runs
  through the program — say "this employer runs a program", never "this job is
  part of it"). Filtering to postings that name the program gives precision and
  perhaps twenty roles. Twenty real ones beat two thousand scraped, but decide
  knowingly.
- Many programs recruit through a dedicated portal, not the main ATS — the
  employer record may need a program-specific application URL.
- Scam exposure is low with ATS sourcing but non-zero; keep the report path.

## Why Phase 1 first

Phase 1 is a day's work, has no moving parts, and plausibly delivers most of the
user value — the federal programs above are free, underused, and unknown to most
people who qualify. Phase 2 is a scheduled pipeline, a new write path, a
manifest to maintain, and an ongoing staleness problem. Ship Phase 1, see whether
anyone asks Autie about work at all, and let that decide whether Phase 2 is worth
its upkeep.
