"""Shared retriever contract: `Retriever.retrieve(query, k) -> list[SearchHit]`.

Fixing this now is what makes future retrievers (BM25 at T2, hybrid/rerank at
T4, metadata filter at T5) directly comparable in the same eval harness.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """One retrieved result.

    ``doc_id`` is the unit golden labels refer to (a Điều). ``passage_id`` may
    be finer-grained when sub-chunking (``chunk_strategy="khoan"``) is on.
    """

    doc_id: str
    score: float
    passage_id: str | None = None
    title: str | None = None
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Retriever(Protocol):
    @property
    def name(self) -> str:
        """Short identifier used to label rows in evaluation reports."""
        ...

    def retrieve(self, query: str, k: int) -> list[SearchHit]:
        """Return at most ``k`` hits, best first, with unique ``doc_id``."""
        ...


def as_tuples(hits: list[SearchHit]) -> list[tuple[str, float]]:
    """The ``[(doc_id, score)]`` shape from docs/plan.md §6."""
    return [(hit.doc_id, hit.score) for hit in hits]


def dedupe_by_doc(hits: list[SearchHit], k: int) -> list[SearchHit]:
    """Collapse passages of the same document, keeping the best-scoring one.

    Required whenever one document can contribute several passages: without
    this, a single article could occupy the whole top-k and Recall@k would
    read far too low.
    """
    best: dict[str, SearchHit] = {}
    for hit in hits:
        current = best.get(hit.doc_id)
        if current is None or hit.score > current.score:
            best[hit.doc_id] = hit
    ordered = sorted(best.values(), key=lambda h: h.score, reverse=True)
    return ordered[:k]
