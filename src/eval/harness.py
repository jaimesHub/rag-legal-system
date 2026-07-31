"""Per-query evaluation harness: run a retriever over golden examples, report metrics + latency.

Reports are **per-query**, not just aggregate. That is what makes regression
comparison possible: two runs can post an identical Recall@10 while a hundred
queries improved and a hundred regressed — only per-query data exposes that
churn (CLAUDE.md: "luôn hỏi bao nhiêu câu tệ đi trước khi nhận một mức lift").
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.eval.metrics import aggregate, metrics_at_k
from src.retrieve.base import Retriever
from src.schemas import GoldenExample


class QueryResult(BaseModel):
    """Everything one query produced. The unit of comparison between runs."""

    query_id: str
    query: str
    expected: list[str]
    ranked: list[str] = Field(description="Retrieved doc_ids, best first")
    scores: list[float] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def hit(self) -> bool:
        return bool(set(self.expected) & set(self.ranked))

    def rank_of_first_relevant(self) -> int | None:
        """1-based rank of the first relevant document, or None if absent."""
        relevant = set(self.expected)
        for rank, doc_id in enumerate(self.ranked, start=1):
            if doc_id in relevant:
                return rank
        return None

    def reciprocal_rank(self) -> float:
        rank = self.rank_of_first_relevant()
        return 1.0 / rank if rank else 0.0


class FailureCase(BaseModel):
    query_id: str
    query: str
    expected: list[str]
    retrieved: list[str]
    top_score: float | None = None


class EvalReport(BaseModel):
    retriever: str
    split: str
    n_queries: int
    ks: list[int]
    metrics: dict[str, float]
    latency_ms: dict[str, float]
    failures: list[FailureCase] = Field(default_factory=list)
    per_query: list[QueryResult] = Field(default_factory=list)
    run_id: str = ""
    label: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""

    @property
    def name(self) -> str:
        return self.label or self.run_id or self.retriever

    @property
    def query_ids(self) -> set[str]:
        return {q.query_id for q in self.per_query}

    def by_query_id(self) -> dict[str, QueryResult]:
        return {q.query_id: q for q in self.per_query}

    def summary_line(self) -> str:
        parts = [
            f"{name}={self.metrics[name]:.4f}"
            for name in sorted(self.metrics)
            if name != "n_queries"
        ]
        return f"{self.name} [{self.split}] " + " ".join(parts)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    # Nearest-rank percentile: no interpolation, so small samples stay honest.
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered) + 0.5) - 1))
    return round(ordered[index], 2)


def compute_run_id(retriever: str, split: str, context: dict[str, Any]) -> str:
    """Short stable id for "same retriever, same config, same data".

    Two runs sharing a run_id should be reproductions of each other; a
    differing id means something in the configuration moved.
    """
    payload = json.dumps(
        {"retriever": retriever, "split": split, "context": context},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=5).hexdigest()


def derive_failures(per_query: list[QueryResult], max_failures: int = 10) -> list[FailureCase]:
    """Total misses, worst first. Derived so it can never disagree with per_query."""
    misses = [q for q in per_query if not q.hit]
    return [
        FailureCase(
            query_id=q.query_id,
            query=q.query,
            expected=q.expected,
            retrieved=q.ranked[:5],
            top_score=q.scores[0] if q.scores else None,
        )
        for q in misses[:max_failures]
    ]


def evaluate_retriever(
    retriever: Retriever,
    examples: list[GoldenExample],
    *,
    ks: list[int],
    split: str,
    max_failures: int = 10,
    label: str = "",
    context: dict[str, Any] | None = None,
) -> EvalReport:
    top_k = max(ks)
    runs: dict[str, list[str]] = {}
    qrels: dict[str, dict[str, int]] = {}
    per_query: list[QueryResult] = []

    for example in examples:
        relevance = example.scores or dict.fromkeys(example.relevant_doc_ids, 1)
        qrels[example.query_id] = relevance

        started = time.perf_counter()
        hits = retriever.retrieve(example.text, top_k)
        latency = (time.perf_counter() - started) * 1000  # per-query, not just total

        ranked = [hit.doc_id for hit in hits]
        runs[example.query_id] = ranked

        # Per-query metrics at every k, so per-query churn can be inspected
        # without recomputing anything later (compare/dashboard, from T2 on).
        query_metrics: dict[str, float] = {}
        for k in ks:
            query_metrics.update(metrics_at_k(ranked, relevance, k))

        per_query.append(
            QueryResult(
                query_id=example.query_id,
                query=example.text,
                expected=example.relevant_doc_ids,
                ranked=ranked,
                scores=[round(hit.score, 6) for hit in hits],
                metrics={name: round(value, 6) for name, value in query_metrics.items()},
                latency_ms=round(latency, 3),
            )
        )

    latencies = [q.latency_ms for q in per_query]
    context = context or {}

    return EvalReport(
        retriever=retriever.name,
        split=split,
        n_queries=len(examples),
        ks=sorted(ks),
        metrics=aggregate(runs, qrels, ks),
        latency_ms={
            "mean": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
        },
        failures=derive_failures(per_query, max_failures),
        per_query=per_query,
        run_id=compute_run_id(retriever.name, split, context),
        label=label,
        context=context,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def save_report(report: EvalReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.created_at.replace(":", "").replace("-", "")
    tag = _slug(report.label) or report.run_id
    path = directory / f"eval_{report.split}_{tag}_{stamp}.json"
    path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_report(path: Path) -> EvalReport:
    return EvalReport.model_validate_json(path.read_text(encoding="utf-8"))


def list_reports(directory: Path) -> list[Path]:
    """Newest first, so a future `compare` command defaults to recent runs."""
    if not directory.exists():
        return []
    return sorted(directory.glob("eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
