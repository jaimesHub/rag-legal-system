"""End-to-end offline smoke test of the whole T0 chain.

Exercises the same layers `make smoke` drives — verify (schema check), golden
(dev/test split with the leakage guard), ingest (chunk + audit), index (embed
+ upsert), evaluate (retrieve + score) — over a couple dozen synthetic legal
documents. No network call and no running Qdrant:

* the three HuggingFace-backed `src.ingest.loader` functions
  (`iter_corpus`, `load_queries`, `load_qrels`) are monkeypatched with an
  in-memory corpus/queries/qrels instead of hitting the real dataset;
* `QdrantStore` is given an in-memory client (`QdrantClient(location=":memory:")`)
  instead of the Docker instance started by `make up`.

This proves the wiring end to end, not retrieval quality — see docs/t0.md
step 17 and CLAUDE.md's note that PROVIDER=fake numbers are a regression
tripwire, never a baseline.
"""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from src.eval import golden as golden_mod
from src.eval.harness import evaluate_retriever
from src.index.qdrant_store import QdrantStore
from src.ingest import loader as loader_mod
from src.ingest import pipeline as pipeline_mod
from src.ingest.loader import CorpusRecord, QrelSet
from src.ingest.pipeline import build_passages, load_passages, write_passages
from src.providers.fake import FakeEmbeddingProvider
from src.retrieve.vector import VectorRetriever
from src.schemas import Query

N_DOCS = 24


def _synthetic_corpus() -> list[CorpusRecord]:
    records = []
    for i in range(1, N_DOCS + 1):
        records.append(
            CorpusRecord(
                doc_id=f"{i:02d}/2021/tt-btc+1",
                title=f"Điều 1. Quy định về nội dung số {i}",
                text=(
                    f"1. Nội dung số {i} quy định về thủ tục hành chính liên quan "
                    f"đến lĩnh vực số {i} của Bộ Tài chính.\n"
                    f"2. Trách nhiệm thi hành thuộc về cơ quan quản lý số {i}."
                ),
            )
        )
    return records


def _synthetic_queries_and_qrels(
    records: list[CorpusRecord],
) -> tuple[dict[str, Query], QrelSet, QrelSet]:
    """Every 3rd document gets a golden test query pointing straight at it."""
    queries: dict[str, Query] = {}
    test_labels: dict[str, dict[str, int]] = {}
    for idx, record in enumerate(records):
        if idx % 3 != 0:
            continue
        query_id = f"q{idx}"
        queries[query_id] = Query(
            query_id=query_id, text=f"thủ tục hành chính lĩnh vực số {idx + 1}"
        )
        test_labels[query_id] = {record.doc_id: 1}

    train = QrelSet(name="train", labels={})
    test = QrelSet(name="test", labels=test_labels)
    return queries, train, test


@pytest.fixture
def synthetic_dataset(monkeypatch):
    """Patch every network-touching loader call with a small offline corpus."""
    records = _synthetic_corpus()
    queries, train, test = _synthetic_queries_and_qrels(records)

    def fake_iter_corpus(settings, limit=None):
        return iter(records[:limit] if limit else records)

    def fake_load_queries(settings):
        return queries, 0  # no duplicate rows dropped

    def fake_load_qrels(settings, split):
        return {"train": train, "test": test}[split]

    # verify_dataset() calls iter_corpus/load_queries/load_qrels as
    # module-globals of src.ingest.loader itself, so patching the module
    # attributes here is enough to reach it.
    monkeypatch.setattr(loader_mod, "iter_corpus", fake_iter_corpus)
    monkeypatch.setattr(loader_mod, "load_queries", fake_load_queries)
    monkeypatch.setattr(loader_mod, "load_qrels", fake_load_qrels)

    # golden.py and pipeline.py each did `from src.ingest.loader import ...`,
    # which binds independent names into their own module namespaces —
    # patching loader_mod above does not reach those, so patch them too.
    monkeypatch.setattr(golden_mod, "load_queries", fake_load_queries)
    monkeypatch.setattr(golden_mod, "load_qrels", fake_load_qrels)
    monkeypatch.setattr(pipeline_mod, "iter_corpus", fake_iter_corpus)

    return records, queries, train, test


def test_verify_dataset_runs_offline_without_raising(settings, synthetic_dataset):
    """verify_dataset must never hit the network — only assert it completes.

    EXPECTED is calibrated to the real ~61k-document corpus, so a synthetic
    24-document corpus is *expected* to fail those checks; this test is only
    about wiring (no exception, a well-formed result), not about all_ok.
    """
    result = loader_mod.verify_dataset(settings)
    assert "checks" in result
    assert result["duplicate_query_rows"] == 0
    assert result["overlap_count"] == 0


def test_full_offline_chain_produces_a_populated_report(settings, synthetic_dataset):
    """verify -> golden -> ingest -> index -> evaluate, no network, no Docker."""
    _records, _queries, _train, test = synthetic_dataset

    # golden: dev/test split off the (patched) qrels.
    stats = golden_mod.build_golden(settings)
    assert stats["test"].n_queries == len(test.labels)
    test_examples = golden_mod.load_golden(settings, "test")
    assert test_examples

    # ingest: chunk the whole synthetic corpus. limit=None (full-corpus mode)
    # sidesteps the gold-covering slice logic, which only matters when
    # limit < corpus size — here the corpus is already tiny.
    passages, audit = build_passages(settings, limit=None)
    write_passages(settings, passages, audit)
    assert audit.documents == N_DOCS
    reloaded = load_passages(settings)
    assert len(reloaded) == len(passages)

    # index: embed with the deterministic fake provider, upsert into an
    # in-memory Qdrant collection (no Docker dependency).
    embedder = FakeEmbeddingProvider(dim=settings.embed_dim)
    store = QdrantStore(settings, client=QdrantClient(location=":memory:"))
    store.ensure_collection(recreate=True)
    vectors = embedder.embed([p.embed_text for p in reloaded], task_type="RETRIEVAL_DOCUMENT")
    store.upsert(reloaded, vectors)
    assert store.count() == len(reloaded)

    # evaluate: retrieve + score against the golden test split.
    retriever = VectorRetriever(store, embedder)
    report = evaluate_retriever(retriever, test_examples, ks=[1, 5, 10], split="test")

    assert report.n_queries > 0
    assert report.n_queries == len(test_examples)
    assert report.latency_ms["mean"] >= 0.0
    # Every gold document was ingested and indexed (full corpus, no slicing),
    # and the corpus has only 24 documents (chance alone is ~10/24=0.42), so
    # this should read very high. A regression tripwire, not a quality claim
    # (CLAUDE.md; docs/t0.md step 17).
    assert report.metrics["recall@10"] > 0.9
