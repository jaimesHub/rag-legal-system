from __future__ import annotations

import math

from src.eval.metrics import aggregate, metrics_at_k


def test_perfect_rank_one_hit():
    m = metrics_at_k(["a", "b", "c"], {"a": 1}, k=3)
    assert m["hit_rate@3"] == 1.0
    assert m["mrr@3"] == 1.0
    assert m["recall@3"] == 1.0
    assert m["map@3"] == 1.0
    assert math.isclose(m["precision@3"], 1 / 3)


def test_mrr_reflects_rank_of_first_hit():
    assert metrics_at_k(["x", "y", "a"], {"a": 1}, k=3)["mrr@3"] == 1 / 3


def test_total_miss_scores_zero():
    m = metrics_at_k(["x", "y"], {"a": 1}, k=2)
    assert m["hit_rate@2"] == 0.0
    assert m["recall@2"] == 0.0
    assert m["ndcg@2"] == 0.0


def test_cutoff_excludes_hits_beyond_k():
    assert metrics_at_k(["x", "a"], {"a": 1}, k=1)["recall@1"] == 0.0


def test_recall_with_multiple_relevant_docs():
    m = metrics_at_k(["a", "x", "y"], {"a": 1, "b": 1}, k=3)
    assert m["recall@3"] == 0.5


def test_map_rewards_ranking_both_hits_higher():
    good = metrics_at_k(["a", "b", "x"], {"a": 1, "b": 1}, k=3)["map@3"]
    bad = metrics_at_k(["a", "x", "b"], {"a": 1, "b": 1}, k=3)["map@3"]
    assert good > bad


def test_ndcg_is_one_for_ideal_ordering():
    m = metrics_at_k(["a", "b"], {"a": 1, "b": 1}, k=2)
    assert math.isclose(m["ndcg@2"], 1.0)


def test_ndcg_uses_graded_relevance_when_present():
    """Binary in this dataset today, but the metric must not ignore grades if added later."""
    better = metrics_at_k(["a", "b"], {"a": 3, "b": 1}, k=2)["ndcg@2"]
    worse = metrics_at_k(["b", "a"], {"a": 3, "b": 1}, k=2)["ndcg@2"]
    assert better > worse
    assert math.isclose(better, 1.0)


def test_empty_ranking_scores_zero_not_error():
    m = metrics_at_k([], {"a": 1}, k=5)
    assert m["recall@5"] == 0.0
    assert m["mrr@5"] == 0.0


def test_aggregate_counts_missing_queries_as_zero():
    """A retriever returning nothing for a query must not shrink the denominator."""
    report = aggregate({"q1": ["a"]}, {"q1": {"a": 1}, "q2": {"b": 1}}, ks=[1])
    assert report["n_queries"] == 2.0
    assert report["recall@1"] == 0.5


def test_aggregate_macro_averages_across_ks():
    report = aggregate({"q1": ["x", "a"]}, {"q1": {"a": 1}}, ks=[1, 2])
    assert report["recall@1"] == 0.0
    assert report["recall@2"] == 1.0


def test_aggregate_on_empty_qrels():
    assert aggregate({}, {}, ks=[1])["n_queries"] == 0.0
