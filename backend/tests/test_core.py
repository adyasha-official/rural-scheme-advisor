"""Offline tests: the LLM / embedding calls are replaced with deterministic fakes."""
import re
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config, ingest, llm, nlp, rag, retriever
from app.main import app

DIM = 128


def fake_embed(texts, task="RETRIEVAL_DOCUMENT"):
    out = np.zeros((len(texts), DIM), dtype="float32")
    for i, t in enumerate(texts):
        for w in re.findall(r"\w+", t.lower()):
            out[i, zlib.crc32(w.encode()) % DIM] += 1
    return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)


CHUNKS = [
    {"id": "pm_kisan_g_p4_c01", "text": "Farmer families owning cultivable land are eligible for income support under the scheme in instalments.",
     "scheme_id": "pm_kisan", "scheme_name": "PM-KISAN", "category": "Agriculture", "document": "g.pdf",
     "document_title": "PM-KISAN - G", "page": 4, "section": "Eligibility", "source_url": "https://x"},
    {"id": "mgnrega_g_p9_c01", "text": "Every rural household whose adult members volunteer for unskilled manual work is entitled to a job card and 100 days of wage employment.",
     "scheme_id": "mgnrega", "scheme_name": "MGNREGA", "category": "Employment", "document": "g.pdf",
     "document_title": "MGNREGA - G", "page": 9, "section": "Employment Guarantee", "source_url": "https://y"},
]


@pytest.fixture(autouse=True)
def patched(monkeypatch):
    monkeypatch.setattr(llm, "embed", fake_embed)
    idx = retriever.Index(CHUNKS, fake_embed([c["text"] for c in CHUNKS]))
    monkeypatch.setattr(retriever, "_index", idx)
    monkeypatch.setattr(rag, "get_index", lambda: idx)
    monkeypatch.setattr(config, "MIN_SCORE", 0.2)
    rag._sessions.clear()


def test_language_detection():
    assert nlp.detect_language("Who is eligible?") == "en"
    assert nlp.detect_language("कौन पात्र है") == "hi"
    assert nlp.detect_language("କିଏ ଯୋଗ୍ୟ") == "or"


def test_scheme_and_intent():
    assert nlp.detect_scheme("Who can apply for PM Kisan?") == "pm_kisan"
    assert nlp.detect_scheme("मनरेगा में काम") == "mgnrega"
    assert nlp.detect_scheme("which scheme helps farmers and housing") is None
    assert nlp.detect_intent("What documents are required?") == "documents"


def test_chunking_limits_and_overlap():
    text = "\n\n".join(" ".join(f"word{i}_{j}" for j in range(60)) for i in range(10))
    pieces, _ = ingest.chunk_page(text, 150, 20, None)
    assert len(pieces) > 1
    assert all(len(t.split()) <= 150 + 20 + 60 for t, _ in pieces)


def test_heading_becomes_section():
    text = "1. ELIGIBILITY\n" + " ".join(["farmer"] * 40)
    pieces, section = ingest.chunk_page(text, 200, 20, None)
    assert section == "1. ELIGIBILITY"


def test_retrieval_ranks_and_filters():
    idx = retriever.get_index()
    q = fake_embed(["job card 100 days wage employment"])[0]
    assert idx.search(q, 2)[0].chunk["scheme_id"] == "mgnrega"
    assert all(h.chunk["scheme_id"] == "pm_kisan" for h in idx.search(q, 2, "pm_kisan"))


def test_citations_are_validated(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda p, s: "Farmers with land are eligible [1]. Fake claim [7].")
    res = rag.answer_question("Who is eligible for PM Kisan farmer land?", "s1")
    assert res["status"] == "answered"
    assert "[7]" not in res["answer"]
    assert res["sources"][0]["page"] == 4 and res["sources"][0]["scheme"] == "PM-KISAN"


def test_uncited_answer_is_rejected(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda p, s: "Sure, here is something without citations.")
    assert rag.answer_question("PM Kisan farmer land eligible", "s2")["status"] == "not_found"


def test_unsupported_query_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(config, "MIN_SCORE", 0.9)
    def boom(*a):
        raise AssertionError("LLM must not be called")
    monkeypatch.setattr(llm, "generate", boom)
    res = rag.answer_question("What is the weather on Mars tomorrow", "s3")
    assert res["status"] == "not_found"


def test_followup_reuses_scheme(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda p, s: "Land-owning farmer families are eligible [1].")
    rag.answer_question("Explain PM Kisan farmer land", "s4")
    assert rag._sessions["s4"]["scheme_id"] == "pm_kisan"
    res = rag.answer_question("Who is eligible?", "s4")
    assert res["scheme_id"] == "pm_kisan"


def test_api_validation_and_health():
    c = TestClient(app)
    assert c.get("/health").json()["status"] == "ok"
    assert c.post("/api/chat", json={"question": "x"}).status_code == 422
    assert c.post("/api/chat", json={"question": "a" * 600}).status_code == 422
    assert len(c.get("/api/schemes").json()) == 5
    assert c.get("/api/schemes/nope").status_code == 404


def test_recommendations():
    c = TestClient(app)
    r = c.post("/api/recommendations", json={"needs": ["housing"], "occupation": "farmer"}).json()
    ids = [x["scheme_id"] for x in r["results"]]
    assert "pmay_g" in ids and "pm_kisan" in ids
    assert "not an eligibility decision" in r["disclaimer"]
