"""Shared data contracts between ingest -> index -> retrieve -> eval.

Kept as a single flat module (rather than a package) since these are the few
structures every layer of the pipeline needs to agree on; splitting them up
would just add import indirection for no benefit at this size.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LegalMetadata(BaseModel):
    """Parsed from a corpus id such as ``01/2009/tt-bnn+1`` plus its title.

    These become the metadata filters of T5 (document type, year, issuer), so
    they're extracted at ingest time even though nothing filters on them yet.
    """

    doc_key: str = Field(description="Document identifier, e.g. 01/2009/tt-bnn")
    doc_number: str | None = None
    year: int | None = None
    doc_code: str | None = Field(default=None, description="Raw code, e.g. tt-bnn, qh14")
    doc_type: str | None = Field(default=None, description="Normalised type, e.g. thong_tu")
    doc_type_label: str | None = None
    issuer: str | None = Field(default=None, description="Issuing body code, e.g. cp, btc")
    article_index: int | None = Field(default=None, description="Index within the document")
    article_no: str | None = Field(default=None, description="Điều number parsed from title")
    article_heading: str | None = None
    khoan_no: str | None = Field(default=None, description="Khoản number when sub-chunked")
    parse_ok: bool = True


class Passage(BaseModel):
    """One indexable unit of text."""

    passage_id: str = Field(description="Unique per chunk; equals doc_id for article chunks")
    doc_id: str = Field(description="Corpus id — the unit golden labels point at")
    title: str
    text: str
    embed_text: str = Field(description="Exactly what gets embedded (title + text)")
    metadata: LegalMetadata


class Query(BaseModel):
    query_id: str
    text: str


class GoldenExample(BaseModel):
    """A query paired with the document ids that answer it."""

    query_id: str
    text: str
    relevant_doc_ids: list[str]
    # Graded relevance is kept even though this dataset is currently binary
    # (every score is 1), so nDCG stays meaningful if graded labels ever
    # arrive later.
    scores: dict[str, int] = Field(default_factory=dict)


class SplitStats(BaseModel):
    """Summary stats for a golden split, for the audit trail in manifest.json."""

    name: str
    n_queries: int
    n_labels: int
    mean_labels_per_query: float
    multi_label_queries: int
    excluded_overlap: int = 0
