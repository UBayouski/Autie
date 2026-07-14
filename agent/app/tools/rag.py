"""Knowledge-base retrieval over Firestore vector search.

Custom RAG per docs/rag-constraints.md: Firestore find_nearest (flat KNN,
COSINE), gemini-embedding-001 at EXACTLY 768 dims on BOTH ingestion and query
paths - a dims mismatch fails silently with garbage similarity, hence the
asserts here and in ingestion/ingest.py.
"""

import logging
import os

from google import genai
from google.genai import types as genai_types
from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

logger = logging.getLogger("autie.rag")

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIMS = 768  # MUST match ingestion/ingest.py
COLLECTION = "rag_chunks"
TOP_K = 6

_genai_client: genai.Client | None = None
_db: firestore.AsyncClient | None = None


def _clients() -> tuple[genai.Client, firestore.AsyncClient]:
    global _genai_client, _db
    if _genai_client is None:
        _genai_client = genai.Client()
    if _db is None:
        _db = firestore.AsyncClient(
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
            database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        )
    return _genai_client, _db


async def search_knowledge_base(question: str) -> dict:
    """Searches Autie's curated knowledge base about autism and related topics.

    Use this FIRST for informational questions: what autism is, signs and
    symptoms, screening and diagnosis, therapies and interventions, prevalence
    and research, education rights. The excerpts come from vetted sources
    (CDC, NIH, MedlinePlus).

    Base your answer on the returned excerpts and cite each source inline as a
    markdown link using its source_title and source_url. If the results don't
    cover the question, say the knowledge base doesn't cover it and answer
    from general knowledge with appropriate care.

    Args:
        question: The user's question, rephrased as a clear standalone query.

    Returns:
        dict with "excerpts": list of {text, source_title, source_url, section},
        or "error" on failure.
    """
    try:
        genai_client, db = _clients()
        result = genai_client.models.embed_content(
            model=EMBED_MODEL,
            contents=question,
            config=genai_types.EmbedContentConfig(
                output_dimensionality=EMBED_DIMS,
                task_type="RETRIEVAL_QUERY",
            ),
        )
        query_vector = result.embeddings[0].values
        assert len(query_vector) == EMBED_DIMS, (
            f"query dims {len(query_vector)} != {EMBED_DIMS}"
        )

        vector_query = db.collection(COLLECTION).find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=TOP_K,
        )
        snapshots = await vector_query.get()
    except Exception:
        logger.exception("knowledge base search failed")
        return {"error": "The knowledge base is temporarily unavailable."}

    excerpts = [
        {
            "text": doc.get("text"),
            "source_title": doc.get("source_title"),
            "source_url": doc.get("source_url"),
            "section": doc.get("section"),
        }
        for doc in snapshots
    ]
    logger.info("kb search ok excerpts=%d", len(excerpts))
    if not excerpts:
        return {"excerpts": [], "note": "No relevant material found."}
    return {"excerpts": excerpts}
