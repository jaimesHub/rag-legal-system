from __future__ import annotations

from src.retrieve.base import SearchHit, as_tuples, dedupe_by_doc


def _hit(doc_id: str, score: float, passage_id: str | None = None) -> SearchHit:
    return SearchHit(doc_id=doc_id, score=score, passage_id=passage_id or doc_id)


def test_dedupe_keeps_the_best_scoring_passage_per_document():
    hits = [_hit("d1", 0.5, "d1#k1"), _hit("d1", 0.9, "d1#k2"), _hit("d2", 0.7)]
    result = dedupe_by_doc(hits, k=10)
    assert [h.doc_id for h in result] == ["d1", "d2"]
    assert result[0].passage_id == "d1#k2"


def test_dedupe_reorders_by_score_after_collapsing():
    hits = [_hit("d1", 0.2), _hit("d2", 0.4), _hit("d1", 0.9)]
    assert [h.doc_id for h in dedupe_by_doc(hits, k=10)] == ["d1", "d2"]


def test_dedupe_applies_k_after_collapsing_not_before():
    """Oversampling only helps if k is enforced on unique documents, not raw hits."""
    hits = [_hit("d1", 0.9, "d1#a"), _hit("d1", 0.8, "d1#b"), _hit("d2", 0.7)]
    result = dedupe_by_doc(hits, k=2)
    assert [h.doc_id for h in result] == ["d1", "d2"]


def test_dedupe_of_empty_list():
    assert dedupe_by_doc([], k=5) == []


def test_as_tuples_matches_the_plan_contract():
    assert as_tuples([_hit("d1", 0.9), _hit("d2", 0.5)]) == [("d1", 0.9), ("d2", 0.5)]
