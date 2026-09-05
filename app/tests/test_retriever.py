"""Pytest suite for the drone knowledge retriever.

Run from the repo root with::

    python -m pytest app/tests/test_retriever.py -v
"""

import pytest

from app.knowledge.retriever import KnowledgeRetriever, chunk_text


@pytest.fixture(scope="module")
def retriever():
    return KnowledgeRetriever()


# ---------------------------------------------------------------------------
# Chunking (no model needed)
# ---------------------------------------------------------------------------


def test_chunk_text_keeps_label_with_value():
    text = "Low confidence:\n0.00 - 0.39\n\nModerate confidence:\n0.40 - 0.59"
    assert chunk_text(text) == [
        "Low confidence: 0.00 - 0.39",
        "Moderate confidence: 0.40 - 0.59",
    ]


def test_chunk_text_merges_wrapped_list_lines():
    text = (
        "Inspection Procedure\n\n"
        "1. Check battery before departure.\n"
        "5. If anomaly confidence is below 0.70,\n"
        "   collect additional evidence."
    )
    chunks = chunk_text(text)
    assert "Inspection Procedure" in chunks
    assert "1. Check battery before departure." in chunks
    assert "5. If anomaly confidence is below 0.70, collect additional evidence." in chunks


def test_chunk_text_ignores_blank_lines():
    assert chunk_text("\n\n  \n") == []
    assert chunk_text("") == []


# ---------------------------------------------------------------------------
# Knowledge base loading
# ---------------------------------------------------------------------------


def test_chunks_loaded_from_all_documents(retriever):
    sources = {chunk.source for chunk in retriever.chunks}
    assert sources == {"anomaly.txt", "history.txt", "inspection.txt"}
    assert len(retriever.chunks) > 0
    assert retriever.embeddings is not None
    assert retriever.embeddings.shape[0] == len(retriever.chunks)


def test_no_fragmented_chunks(retriever):
    """Labels must stay joined with their values (the old ``split("\\n")``
    bug produced chunks like ``"0.00 - 0.39"`` or ``"Recommended action:"``)."""
    fragments = {
        "0.00 - 0.39",
        "0.40 - 0.59",
        "0.60 - 1.00",
        "Recommended action:",
        "Previous inspection:",
    }
    texts = {chunk.text for chunk in retriever.chunks}
    assert not (fragments & texts), f"fragmented chunks found: {fragments & texts}"
    for chunk in retriever.chunks:
        assert chunk.text.strip(), "chunk text must not be empty"


def test_default_dir_is_cwd_independent(tmp_path, monkeypatch):
    """KnowledgeRetriever() must work regardless of the caller's CWD."""
    monkeypatch.chdir(tmp_path)
    assert len(KnowledgeRetriever().chunks) > 0


def test_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        KnowledgeRetriever(knowledge_dir=tmp_path / "does-not-exist")


def test_empty_directory_raises(tmp_path):
    with pytest.raises(ValueError, match="No .txt documents"):
        KnowledgeRetriever(knowledge_dir=tmp_path)


def test_custom_directory_loads(tmp_path):
    doc = tmp_path / "custom.txt"
    doc.write_text("Battery Rule\n\nAlways check battery before departure.\n", encoding="utf-8")
    custom = KnowledgeRetriever(knowledge_dir=tmp_path)
    assert [c.source for c in custom.chunks] == ["custom.txt"] * len(custom.chunks)
    results = custom.retrieve("battery check", top_k=1)
    assert results[0]["source"] == "custom.txt"


# ---------------------------------------------------------------------------
# Retrieval relevance
# ---------------------------------------------------------------------------


def test_retrieve_low_confidence_query(retriever):
    results = retriever.retrieve(
        "What should I do when anomaly confidence is low?", top_k=2
    )
    assert len(results) == 2
    top = results[0]
    assert top["source"] == "inspection.txt"
    assert "0.70" in top["text"] and "additional evidence" in top["text"]


def test_retrieve_battery_query(retriever):
    results = retriever.retrieve(
        "What are the battery safety requirements?", top_k=2
    )
    assert len(results) == 2
    assert results[0]["source"] == "inspection.txt"
    assert "battery" in results[0]["text"].lower()


def test_retrieve_history_query(retriever):
    results = retriever.retrieve(
        "Has this area had previous anomalies?", top_k=2
    )
    assert len(results) == 2
    assert results[0]["source"] == "history.txt"
    assert "previous" in results[0]["text"].lower()


# ---------------------------------------------------------------------------
# Retrieval contract
# ---------------------------------------------------------------------------


def test_retrieve_result_shape_and_ordering(retriever):
    results = retriever.retrieve("anomaly evidence", top_k=3)
    assert len(results) == 3
    for result in results:
        assert set(result) == {"source", "text", "score"}
        assert isinstance(result["source"], str)
        assert isinstance(result["text"], str)
        assert -1.0 <= result["score"] <= 1.0
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_top_k_respected_and_clamped(retriever):
    assert len(retriever.retrieve("anomaly", top_k=1)) == 1
    clamped = retriever.retrieve("anomaly", top_k=10_000)
    assert len(clamped) == len(retriever.chunks)


@pytest.mark.parametrize("bad_query", ["", "   ", None, 123])
def test_retrieve_rejects_bad_query(retriever, bad_query):
    with pytest.raises(ValueError, match="non-empty string"):
        retriever.retrieve(bad_query)


@pytest.mark.parametrize("bad_k", [0, -1, "3", 2.5])
def test_retrieve_rejects_bad_top_k(retriever, bad_k):
    with pytest.raises(ValueError, match="positive integer"):
        retriever.retrieve("anomaly", top_k=bad_k)
