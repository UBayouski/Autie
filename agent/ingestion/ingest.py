"""RAG ingestion: fetch corpus sources, chunk, embed, write to Firestore.

Run from agent/ with the venv and ADC configured:
    .venv/Scripts/python.exe -m ingestion.ingest

Guardrails (docs/rag-constraints.md): gemini-embedding-001 at EXACTLY 768 dims
(Firestore vector index cap is 2048; the model default 3072 would overflow),
own chunker, license tracked per source, chunk count reported.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector

from .chunker import chunk_html

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIMS = 768  # MUST match app/tools/rag.py query-side dims
COLLECTION = "rag_chunks"

_UA = {"User-Agent": "Mozilla/5.0 (compatible; AutieIngest/1.0)"}


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


def main() -> int:
    manifest = json.loads((Path(__file__).parent / "corpus.json").read_text("utf-8"))
    genai_client = genai.Client()
    db = firestore.Client(
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        database=os.getenv("FIRESTORE_DATABASE", "(default)"),
    )
    collection = db.collection(COLLECTION)

    total_chunks = 0
    failures = []
    for source in manifest["sources"]:
        url = source["url"]
        try:
            response = httpx.get(url, headers=_UA, timeout=30, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            failures.append((url, str(exc)))
            print(f"FETCH FAILED {url}: {exc}")
            continue

        chunks = chunk_html(response.text)
        print(f"{source['source_title']}: {len(chunks)} chunks")
        for index, chunk in enumerate(chunks):
            doc_id = hashlib.sha1(f"{url}#{index}".encode()).hexdigest()
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
    return 0 if total_chunks > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
