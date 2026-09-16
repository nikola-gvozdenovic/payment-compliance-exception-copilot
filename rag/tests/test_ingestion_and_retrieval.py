from rag.ingestion import ingest
from rag.retriever import retrieve


def test_ingest_returns_chunk_count_matching_corpus(tmp_path):
    count = ingest(persist_path=tmp_path)
    assert count > 40


def test_ingest_is_idempotent(tmp_path):
    first = ingest(persist_path=tmp_path)
    second = ingest(persist_path=tmp_path)
    assert first == second


def test_retrieve_eur_gbp_corridor_rule_returns_relevant_chunk_in_top_results(tmp_path):
    ingest(persist_path=tmp_path)

    results = retrieve("EUR to GBP corridor rule", k=3, persist_path=tmp_path)

    assert any(r.doc_id == "JUR-0001" for r in results)


def test_retrieve_returns_citation_metadata(tmp_path):
    ingest(persist_path=tmp_path)

    results = retrieve("EUR to GBP corridor rule", k=3, persist_path=tmp_path)

    assert len(results) == 3
    for r in results:
        assert r.chunk_id
        assert r.chunk_id.startswith(f"{r.doc_id}::chunk-")
        assert r.metadata.get("doc_type")


def test_retrieve_on_empty_store_returns_empty_list(tmp_path):
    results = retrieve("anything", k=3, persist_path=tmp_path)
    assert results == []
