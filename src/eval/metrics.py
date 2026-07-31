"""Retrieval metrics: Recall, Precision, MRR, nDCG, MAP, hit_rate @ k.

Kept graded-aware even though this dataset's qrels are currently binary
(every score observed so far is 1): if graded labels arrive later, nDCG stays
meaningful with no change here (see src/schemas.py GoldenExample.scores).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

_EPS = 1e-12


def _dcg(gains: Sequence[float]) -> float:
    return sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))


def metrics_at_k(
    ranked_doc_ids: Sequence[str], relevance: Mapping[str, int], k: int
) -> dict[str, float]:
    """Metrics for one query at cutoff k.

    ``ranked_doc_ids`` must already be deduplicated and ordered best-first
    (see src.retrieve.base.dedupe_by_doc).
    """
    relevant = {doc_id for doc_id, score in relevance.items() if score > 0}
    top = list(ranked_doc_ids[:k])

    hits = [doc_id for doc_id in top if doc_id in relevant]
    n_relevant = len(relevant)

    precision = len(hits) / k if k else 0.0
    recall = len(hits) / n_relevant if n_relevant else 0.0
    hit_rate = 1.0 if hits else 0.0

    first_rank = next((rank for rank, doc_id in enumerate(top, start=1) if doc_id in relevant), 0)
    mrr = 1.0 / first_rank if first_rank else 0.0

    # Average precision, normalised by the reachable number of relevant docs.
    running = 0
    precision_sum = 0.0
    for rank, doc_id in enumerate(top, start=1):
        if doc_id in relevant:
            running += 1
            precision_sum += running / rank
    denominator = min(n_relevant, k)
    average_precision = precision_sum / denominator if denominator else 0.0

    gains = [float(relevance.get(doc_id, 0)) for doc_id in top]
    ideal = sorted((float(s) for s in relevance.values() if s > 0), reverse=True)[:k]
    idcg = _dcg(ideal)
    ndcg = _dcg(gains) / idcg if idcg > _EPS else 0.0

    return {
        f"hit_rate@{k}": hit_rate,
        f"precision@{k}": precision,
        f"recall@{k}": recall,
        f"mrr@{k}": mrr,
        f"map@{k}": average_precision,
        f"ndcg@{k}": ndcg,
    }


def aggregate(
    runs: Mapping[str, Sequence[str]],
    qrels: Mapping[str, Mapping[str, int]],
    ks: Sequence[int],
) -> dict[str, float]:
    """Macro-average metrics over queries.

    Every query in ``qrels`` counts, including ones absent from ``runs`` — a
    retriever that returns nothing for a query scores 0 rather than being
    silently excluded from the denominator.
    """
    if not ks:
        raise ValueError("ks must not be empty")
    if not qrels:
        return {"n_queries": 0.0}

    totals: dict[str, float] = {}
    for query_id, relevance in qrels.items():
        ranked = runs.get(query_id, [])
        for k in ks:
            for name, value in metrics_at_k(ranked, relevance, k).items():
                totals[name] = totals.get(name, 0.0) + value

    n = len(qrels)
    report = {name: round(total / n, 4) for name, total in sorted(totals.items())}
    report["n_queries"] = float(n)
    return report
