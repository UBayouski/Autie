# RAG Implementation Guardrails (Firestore custom RAG)

Hard constraints for the RAG build. Decided 2026-07 during architecture validation —
re-read this before writing or reviewing any ingestion/retrieval code.

Context: custom RAG on **Firestore native vector search** (`find_nearest` + vector
index). Viable and nearly free at our scale (curated corpus, hobby/community traffic).

## 1. Never use Vertex AI Vector Search or RAG Engine

- Vertex AI Vector Search bills for **always-on serving nodes (~$500+/month minimum)**
  regardless of traffic. Prohibited for this project.
- Vertex AI RAG Engine can switch its backing store to **Spanner** — same runaway-cost
  trap (known from past experience). Prohibited.
- Firestore vector search replaces both at our corpus size. If someone proposes either
  product in a PR or design doc, that's a red flag — escalate before merging.

## 2. Embedding dimensions: 768, fixed

- Firestore's vector index caps at **2048 dimensions**; `gemini-embedding-001` defaults
  to **3072** — the default will fail/overflow the index.
- Always set `output_dimensionality=768`. The model is Matryoshka-trained, so truncation
  is supported and quality loss is minimal; storage is 4× cheaper than 3072.
- Query-time embeddings MUST use the same model + same 768 dims as ingestion. A
  mismatch fails silently (garbage similarity scores), so assert dims in code on both
  paths.

## 3. No keyword/BM25 search — design around it

- Firestore offers **no hybrid search**. Pure vector retrieval misses exact terms and
  acronyms (IEP, ABA, ESDM, AAC, …).
- Accepted as tolerable for a small curated corpus. Mitigation: every chunk stores a
  `tags[]` / keywords field populated at ingestion; retrieval may apply an equality
  pre-filter on it for acronym-heavy queries.
- Do NOT attempt to bolt a hybrid-search product on to fix this (see constraint 1).
  If retrieval quality on acronyms proves bad in evals, improve tagging first.

## 4. Flat-index scaling ceiling: revisit at tens of thousands of chunks

- Firestore KNN is effectively a **brute-force flat index**: read cost and latency scale
  linearly with corpus size.
- Fine up to **tens of thousands of chunks** — a curated literature base should stay
  under that. Track chunk count in the ingestion manifest.
- If the corpus approaches ~50k+ chunks, that is the trigger to revisit the storage
  choice — not before. Do not pre-optimize for scale we don't have.

## 5. Chunking: own Python script, not Vertex chunker / Document AI

- Skip Vertex chunker and Document AI Layout Parser unless sources turn out to be messy
  PDFs that a simple parser can't handle.
- A heading-aware Python chunking script we control (~500–800 tokens, ~10% overlap) is
  simpler and free, and must attach **source/page/section metadata to every chunk** so
  answers can cite sources.

---

See [architecture.md](architecture.md) § "RAG — custom on Firestore vector search" for
the full pipeline design these constraints apply to.
