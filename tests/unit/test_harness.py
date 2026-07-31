from __future__ import annotations

from src.eval.harness import evaluate_retriever
from src.retrieve.base import SearchHit
from src.schemas import GoldenExample


class _FakeRetriever:
    """Deterministic in-memory retriever: doc_id -> ranked doc_ids, no I/O."""

    def __init__(self, runs: dict[str, list[str]]) -> None:
        self._runs = runs

    @property
    def name(self) -> str:
        return "fake-test-retriever"

    def retrieve(self, query: str, k: int) -> list[SearchHit]:
        ranked = self._runs.get(query, [])[:k]
        return [SearchHit(doc_id=doc_id, score=1.0 - i * 0.1) for i, doc_id in enumerate(ranked)]


def _examples() -> list[GoldenExample]:
    return [
        GoldenExample(query_id="q1", text="q1", relevant_doc_ids=["a"]),
        GoldenExample(query_id="q2", text="q2", relevant_doc_ids=["b"]),
        GoldenExample(query_id="q3", text="q3", relevant_doc_ids=["z"]),  # total miss
    ]


def test_evaluate_retriever_reports_n_queries_and_latency():
    retriever = _FakeRetriever({"q1": ["a", "x"], "q2": ["x", "b"], "q3": ["x", "y"]})
    report = evaluate_retriever(retriever, _examples(), ks=[1, 5], split="test")

    assert report.n_queries == 3
    assert report.latency_ms["mean"] >= 0.0
    assert all(q.latency_ms >= 0.0 for q in report.per_query)
    assert len(report.per_query) == 3


def test_evaluate_retriever_records_hits_and_misses():
    retriever = _FakeRetriever({"q1": ["a", "x"], "q2": ["x", "b"], "q3": ["x", "y"]})
    report = evaluate_retriever(retriever, _examples(), ks=[1, 5], split="test")

    by_id = report.by_query_id()
    assert by_id["q1"].hit is True
    assert by_id["q2"].hit is True
    assert by_id["q3"].hit is False
    assert report.metrics["recall@5"] > 0.0
    # Exactly one total miss (q3) should surface in failures.
    assert [f.query_id for f in report.failures] == ["q3"]


def test_run_id_is_stable_for_the_same_config():
    retriever = _FakeRetriever({"q1": ["a"]})
    examples = [GoldenExample(query_id="q1", text="q1", relevant_doc_ids=["a"])]
    context = {"provider": "fake", "embed_model": "fake-embedding"}

    report_a = evaluate_retriever(retriever, examples, ks=[1], split="test", context=context)
    report_b = evaluate_retriever(retriever, examples, ks=[1], split="test", context=context)
    assert report_a.run_id == report_b.run_id
