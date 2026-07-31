from __future__ import annotations

import pytest

from src.ingest import pipeline as pipeline_mod
from src.ingest.loader import CorpusRecord
from src.schemas import GoldenExample


def _example(qid: str, docs: list[str]) -> GoldenExample:
    return GoldenExample(
        query_id=qid, text=f"q {qid}", relevant_doc_ids=docs, scores=dict.fromkeys(docs, 1)
    )


def test_gold_coverage_respects_the_budget():
    dev = [_example(f"q{i}", [f"g{i}"]) for i in range(20)]
    gold_ids, covered = pipeline_mod.plan_gold_coverage(dev, limit=10, gold_fraction=0.5)
    assert len(gold_ids) <= 5
    assert len(covered) == len(gold_ids)


def test_gold_coverage_returns_every_query_for_the_full_corpus():
    dev = [_example("q1", ["g1"])]
    gold_ids, covered = pipeline_mod.plan_gold_coverage(dev, limit=None)
    assert gold_ids == set()
    assert covered == dev


def test_gold_coverage_keeps_multi_label_queries_whole():
    """A query is only 'covered' if all of its gold documents fit."""
    dev = [_example("q1", ["a", "b", "c"]), _example("q2", ["d"])]
    gold_ids, covered = pipeline_mod.plan_gold_coverage(dev, limit=4, gold_fraction=0.5)
    # Budget of 2 cannot hold q1's three documents, so nothing is covered.
    assert covered == []
    assert gold_ids == set()


@pytest.fixture
def fake_corpus(monkeypatch):
    records = [
        CorpusRecord(
            doc_id=f"0{i}/2020/tt-btc+{i}",
            title=f"Điều {i}. Mục {i}",
            text=f"1. Nội dung {i} đủ dài để giữ lại.",
        )
        for i in range(1, 21)
    ]
    monkeypatch.setattr(pipeline_mod, "iter_corpus", lambda settings, limit=None: iter(records))
    return records


def test_gold_documents_are_forced_into_the_slice(settings, fake_corpus):
    """The whole point of the gold-covering slice: late gold docs must appear
    even though the natural file order would leave them out of a 5-doc slice."""
    gold = {"019/2020/tt-btc+19"}
    passages, audit = pipeline_mod.build_passages(settings, limit=5, gold_doc_ids=gold)
    assert audit.gold_documents_found == 1
    assert "019/2020/tt-btc+19" in {p.doc_id for p in passages}


def test_slice_respects_the_document_budget(settings, fake_corpus):
    gold = {"019/2020/tt-btc+19"}
    _, audit = pipeline_mod.build_passages(settings, limit=5, gold_doc_ids=gold)
    assert audit.documents == 5


def test_missing_gold_ids_are_reported_not_raised(settings, fake_corpus):
    _, audit = pipeline_mod.build_passages(settings, limit=5, gold_doc_ids={"nope+1"})
    assert audit.gold_documents_missing == ["nope+1"]
    assert audit.gold_documents_found == 0


def test_full_corpus_ingest_takes_everything(settings, fake_corpus):
    _, audit = pipeline_mod.build_passages(settings, limit=None)
    assert audit.documents == 20


def test_audit_records_doc_types_and_year_range(settings, fake_corpus):
    _, audit = pipeline_mod.build_passages(settings, limit=None)
    assert audit.doc_type_counts == {"thong_tu": 20}
    assert audit.year_min == audit.year_max == 2020


def test_audit_records_char_length_percentiles(settings, fake_corpus):
    """T3+ needs this to catch silent truncation of long Điều before it ever
    calls a real embedding API (docs/t0.md pitfall #5)."""
    _, audit = pipeline_mod.build_passages(settings, limit=None)
    assert audit.chars_mean > 0
    assert audit.chars_p50 <= audit.chars_p90 <= audit.chars_p99 <= audit.chars_max


def test_passages_round_trip_through_disk(settings, fake_corpus):
    passages, audit = pipeline_mod.build_passages(settings, limit=None)
    pipeline_mod.write_passages(settings, passages, audit)
    reloaded = pipeline_mod.load_passages(settings)
    assert [p.passage_id for p in reloaded] == [p.passage_id for p in passages]


def test_load_passages_without_ingest_raises_actionable_error(settings):
    with pytest.raises(FileNotFoundError, match="make ingest"):
        pipeline_mod.load_passages(settings)
