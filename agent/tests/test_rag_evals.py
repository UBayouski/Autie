"""Retrieval quality evals - opt-in (needs ADC, a built index, and $0.0x of
embeddings): RUN_RAG_EVALS=1 .venv/Scripts/python.exe -m pytest tests/test_rag_evals.py -v
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

if not os.getenv("RUN_RAG_EVALS"):
    pytest.skip("set RUN_RAG_EVALS=1 to run retrieval evals", allow_module_level=True)

from app.tools.rag import search_knowledge_base

CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "evals" / "retrieval_eval.json").read_text("utf-8")
)["cases"]


@pytest.fixture(scope="module")
def results():
    # One event loop for all queries: the tool caches an AsyncClient that is
    # bound to the loop it was created in (fine in the single-loop server).
    async def run_all():
        return {c["question"]: await search_knowledge_base(c["question"]) for c in CASES}

    return asyncio.run(run_all())


@pytest.mark.parametrize("case", CASES, ids=[c["question"][:40] for c in CASES])
def test_retrieval(case, results):
    result = results[case["question"]]
    assert "excerpts" in result, result
    urls = [e["source_url"] for e in result["excerpts"]]
    assert any(case["expect_url_contains"] in u for u in urls), (
        f"expected a url containing {case['expect_url_contains']!r} in top results, got: {urls}"
    )
