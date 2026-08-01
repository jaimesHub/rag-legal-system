"""Compare two eval runs (intra-project).

The reason this module exists rather than a diff of two metric tables: aggregate
metrics hide churn. A change can leave Recall@10 untouched while moving a hundred
queries in each direction, and that churn is the interesting part.

The other job here is refusing to mislead. A smoke run covers a slice of the test
queries while a real baseline covers all 788; subtracting those aggregates
produces a number that means nothing. So comparison always happens over the
**intersection** of query sets, and the intersection size is reported alongside
every delta.

Ported from the sample project (aie-rag-sample-project/src/eval/compare.py) — the
EvalReport/QueryResult contract is identical between the two repos. Reused here so
`compare_sample` does not duplicate the split-refusal / intersection philosophy.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.eval.harness import EvalReport, QueryResult

# Per-query signal used to decide whether a query got better or worse. Reciprocal
# rank is the right default: it is sensitive to movement in the top ranks, which is
# where a legal lookup either succeeds or fails.
DEFAULT_SIGNAL = "reciprocal_rank"


class QueryDelta(BaseModel):
    query_id: str
    query: str
    expected: list[str]
    rank_a: int | None = None
    rank_b: int | None = None
    signal_a: float = 0.0
    signal_b: float = 0.0
    ranked_a: list[str] = Field(default_factory=list)
    ranked_b: list[str] = Field(default_factory=list)

    @property
    def delta(self) -> float:
        return self.signal_b - self.signal_a

    @property
    def bucket(self) -> str:
        if self.delta > 0:
            return "improved"
        if self.delta < 0:
            return "regressed"
        return "unchanged"


class Comparison(BaseModel):
    name_a: str
    name_b: str
    split: str
    n_queries_a: int
    n_queries_b: int
    n_common: int
    metric_deltas: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="metric -> {a, b, delta}"
    )
    query_deltas: list[QueryDelta] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def comparable(self) -> bool:
        """False when the runs barely overlap — deltas would be noise."""
        return self.n_common > 0 and not any("do not overlap" in w for w in self.warnings)

    def bucket_counts(self) -> dict[str, int]:
        counts = {"improved": 0, "regressed": 0, "unchanged": 0}
        for delta in self.query_deltas:
            counts[delta.bucket] += 1
        return counts

    def movers(self, bucket: str, limit: int = 10) -> list[QueryDelta]:
        """Biggest movers in one direction — the queries worth reading."""
        selected = [d for d in self.query_deltas if d.bucket == bucket]
        reverse = bucket == "improved"
        return sorted(selected, key=lambda d: d.delta, reverse=reverse)[:limit]


def _signal(result: QueryResult, signal: str) -> float:
    if signal == DEFAULT_SIGNAL:
        return result.reciprocal_rank()
    value = result.metrics.get(signal)
    if value is None:
        raise KeyError(
            f"{signal!r} is not a per-query metric in this report. "
            f"Available: {sorted(result.metrics)[:6]}… or {DEFAULT_SIGNAL!r}."
        )
    return value


def compare_reports(a: EvalReport, b: EvalReport, *, signal: str = DEFAULT_SIGNAL) -> Comparison:
    """Compare run ``a`` (baseline) against run ``b`` (candidate)."""
    if a.split != b.split:
        raise ValueError(
            f"Refusing to compare different splits: {a.split!r} vs {b.split!r}. "
            "Metrics from different golden sets are not comparable."
        )

    warnings: list[str] = []
    ids_a, ids_b = a.query_ids, b.query_ids
    common = ids_a & ids_b

    if not a.per_query or not b.per_query:
        warnings.append(
            "One run has no per-query data (produced before per-query reports existed); "
            "only aggregate metrics can be shown, and only if the query sets match."
        )
    if ids_a != ids_b:
        warnings.append(
            f"Query sets differ: {len(ids_a)} vs {len(ids_b)}, {len(common)} in common. "
            "Aggregate metrics below are computed over each run's OWN query set and are "
            "therefore NOT directly comparable — trust the per-query table instead."
        )
    if not common and (a.per_query or b.per_query):
        warnings.append(
            "The two runs do not overlap on a single query. There is nothing to compare."
        )

    metric_deltas: dict[str, dict[str, float]] = {}
    for metric in sorted(set(a.metrics) | set(b.metrics)):
        if metric == "n_queries":
            continue
        value_a = a.metrics.get(metric)
        value_b = b.metrics.get(metric)
        if value_a is None or value_b is None:
            continue
        metric_deltas[metric] = {
            "a": round(value_a, 4),
            "b": round(value_b, 4),
            "delta": round(value_b - value_a, 4),
        }

    lookup_a, lookup_b = a.by_query_id(), b.by_query_id()
    query_deltas: list[QueryDelta] = []
    for query_id in sorted(common):
        qa, qb = lookup_a[query_id], lookup_b[query_id]
        query_deltas.append(
            QueryDelta(
                query_id=query_id,
                query=qb.query,
                expected=qb.expected,
                rank_a=qa.rank_of_first_relevant(),
                rank_b=qb.rank_of_first_relevant(),
                signal_a=_signal(qa, signal),
                signal_b=_signal(qb, signal),
                ranked_a=qa.ranked[:5],
                ranked_b=qb.ranked[:5],
            )
        )

    return Comparison(
        name_a=a.name,
        name_b=b.name,
        split=a.split,
        n_queries_a=a.n_queries,
        n_queries_b=b.n_queries,
        n_common=len(common),
        metric_deltas=metric_deltas,
        query_deltas=query_deltas,
        warnings=warnings,
    )
