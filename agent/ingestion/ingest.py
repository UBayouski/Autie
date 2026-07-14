"""RAG ingestion: fetch corpus sources, chunk, embed, write to Firestore.

Run from agent/ with the venv and ADC configured:
    .venv/Scripts/python.exe -m ingestion.ingest [--dry-run] [--prune]

Writes are upserts keyed by sha1(url#index), so a plain run refreshes every
chunk in place but leaves orphans behind when a source is dropped from the
manifest or a page shrinks to fewer chunks. --prune sweeps those; it runs
AFTER a successful ingest rather than wiping first, so a mid-run failure can
never leave the collection empty and serving nothing.

Guardrails (docs/rag-constraints.md): gemini-embedding-001 at EXACTLY 768 dims
(Firestore vector index cap is 2048; the model default 3072 would overflow),
own chunker, license tracked per source, chunk count reported.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# Windows consoles default to cp1252; source pages contain non-ASCII.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector

from .chunker import chunk_html, chunk_jats

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIMS = 768  # MUST match app/tools/rag.py query-side dims
COLLECTION = "rag_chunks"
_DELETE_BATCH = 400  # Firestore caps a write batch at 500

_UA = {"User-Agent": "Mozilla/5.0 (compatible; AutieIngest/1.0)"}

# PMC serves a reCAPTCHA interstitial to scripted clients, so scraping the
# article page silently yields "Checking your browser" HTML instead of the
# paper. E-utilities is NCBI's supported route and returns JATS full text.
_PMC_ID = re.compile(r"/(?:pmc/)?articles/(PMC\d+)")
_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def fetch_source(url: str) -> tuple[str, bool]:
    """Returns (document_text, is_jats) for a corpus URL."""
    pmc_match = _PMC_ID.search(url)
    if pmc_match:
        response = httpx.get(
            _EFETCH,
            params={"db": "pmc", "id": pmc_match.group(1).removeprefix("PMC")},
            headers=_UA,
            timeout=60,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text, True

    response = httpx.get(url, headers=_UA, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.text, False


def embed_document(client: genai.Client, text: str) -> list[float]:
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=genai_types.EmbedContentConfig(
            output_dimensionality=EMBED_DIMS,
            task_type="RETRIEVAL_DOCUMENT",
        ),
    )
    values = result.embeddings[0].values
    assert len(values) == EMBED_DIMS, f"expected {EMBED_DIMS} dims, got {len(values)}"
    return values


def prune(db: firestore.Client, collection, keep_ids: set[str]) -> int:
    """Deletes chunks not written by this run. Returns the number removed."""
    # select([]) fetches ids only - no point pulling 768-dim vectors back just
    # to decide what to delete.
    stale = [
        doc.reference
        for doc in collection.select([]).stream()
        if doc.id not in keep_ids
    ]
    for start in range(0, len(stale), _DELETE_BATCH):
        batch = db.batch()
        for reference in stale[start:start + _DELETE_BATCH]:
            batch.delete(reference)
        batch.commit()
    return len(stale)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and chunk only; no embedding calls, no Firestore writes",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="after a clean ingest, delete chunks no longer in the manifest",
    )
    args = parser.parse_args()

    manifest = json.loads((Path(__file__).parent / "corpus.json").read_text("utf-8"))

    genai_client = None if args.dry_run else genai.Client()
    collection = None
    if not args.dry_run:
        db = firestore.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        )
        collection = db.collection(COLLECTION)

    total_chunks = 0
    written_ids: set[str] = set()
    failures = []
    for source in manifest["sources"]:
        url = source["url"]
        try:
            document, is_jats = fetch_source(url)
        except httpx.HTTPError as exc:
            failures.append((url, str(exc)))
            print(f"FETCH FAILED {url}: {exc}")
            continue

        chunks = chunk_jats(document) if is_jats else chunk_html(document)
        if not chunks:
            failures.append((url, "no chunks extracted"))
            print(f"EMPTY {url}: no chunks extracted")
            continue

        print(f"{source['source_title']}: {len(chunks)} chunks")
        for index, chunk in enumerate(chunks):
            doc_id = hashlib.sha1(f"{url}#{index}".encode()).hexdigest()
            written_ids.add(doc_id)
            if args.dry_run:
                continue
            embedding = embed_document(genai_client, chunk.text)
            collection.document(doc_id).set({
                "text": chunk.text,
                "embedding": Vector(embedding),
                "source_title": source["source_title"],
                "source_url": url,
                "license": source["license"],
                "section": chunk.section,
                "tags": source.get("tags", []),
            })
        total_chunks += len(chunks)

    print(f"\nDone: {total_chunks} chunks from "
          f"{len(manifest['sources']) - len(failures)}/{len(manifest['sources'])} sources")
    if failures:
        print("Failed sources (fix or replace URLs in corpus.json):")
        for url, error in failures:
            print(f"  - {url}: {error}")

    if args.dry_run:
        print("Dry run: nothing embedded or written.")
    elif args.prune and total_chunks > 0:
        # A source that failed to fetch has no fresh chunks in written_ids, so
        # pruning now would delete its still-good chunks and quietly shrink the
        # corpus. Fix the source first, then prune.
        if failures:
            print("\nSKIPPED --prune: some sources failed this run; pruning would "
                  "delete their existing chunks. Resolve the failures above and "
                  "re-run with --prune.")
        else:
            removed = prune(db, collection, written_ids)
            print(f"Pruned {removed} stale chunk(s) no longer in the manifest.")

    return 0 if total_chunks > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
