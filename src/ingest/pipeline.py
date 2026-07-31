"""Ingest orchestration: corpus -> cleaned, chunked, metadata-tagged passages.

**Why the T0 slice is "gold-covering".** T0 scope is `limit=500` documents out of
the ~61k corpus. Taking the first 500 in file order would contain the gold
document for almost no golden query, so every metric would read 0.00 and the
smoke test would prove nothing about the wiring. Instead the slice is built as:

    gold documents for as many test queries as fit half the budget
  + the next documents in file order as distractors (the rest of the budget)

Metrics computed on this slice are therefore **optimistic by design** — the
corpus is ~120x smaller than the real one and (for the covered queries) the
answer is guaranteed to be present. This is a wiring/regression check, not a
quality claim; the honest full-corpus number arrives once T3 runs `limit=0`.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import Settings
from src.ingest.chunk import chunk_document
from src.ingest.loader import iter_corpus
from src.schemas import GoldenExample, Passage

logger = logging.getLogger(__name__)

PASSAGES_FILE = "passages.jsonl"
AUDIT_FILE = "ingest_audit.json"


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered) + 0.5) - 1))
    return ordered[index]


@dataclass
class IngestAudit:
    documents: int = 0
    passages: int = 0
    metadata_parse_failures: int = 0
    empty_text: int = 0
    gold_documents_found: int = 0
    gold_documents_missing: list[str] = field(default_factory=list)
    doc_type_counts: dict[str, int] = field(default_factory=dict)
    year_min: int | None = None
    year_max: int | None = None
    chars_mean: float = 0.0
    chars_p50: int = 0
    chars_p90: int = 0
    chars_p99: int = 0
    chars_max: int = 0

    def to_dict(self) -> dict:
        return {
            "documents": self.documents,
            "passages": self.passages,
            "metadata_parse_failures": self.metadata_parse_failures,
            "empty_text": self.empty_text,
            "gold_documents_found": self.gold_documents_found,
            "gold_documents_missing": self.gold_documents_missing,
            "doc_type_counts": self.doc_type_counts,
            "year_range": [self.year_min, self.year_max],
            "chars_mean": self.chars_mean,
            "chars_p50": self.chars_p50,
            "chars_p90": self.chars_p90,
            "chars_p99": self.chars_p99,
            "chars_max": self.chars_max,
        }


def plan_gold_coverage(
    dev: list[GoldenExample], limit: int | None, gold_fraction: float = 0.5
) -> tuple[set[str], list[GoldenExample]]:
    """Pick which golden queries the slice will be able to answer.

    Returns the gold document ids to force into the slice, and the golden
    examples fully covered by them. With ``limit=None`` (full corpus) every
    query is covered and nothing needs forcing.
    """
    if limit is None:
        return set(), dev

    budget = max(1, int(limit * gold_fraction))
    gold_ids: set[str] = set()
    covered: list[GoldenExample] = []
    for example in dev:
        candidate = gold_ids | set(example.relevant_doc_ids)
        if len(candidate) > budget:
            break
        gold_ids = candidate
        covered.append(example)
    return gold_ids, covered


def build_passages(
    settings: Settings,
    *,
    limit: int | None,
    gold_doc_ids: set[str] | None = None,
) -> tuple[list[Passage], IngestAudit]:
    """Single streaming pass over the corpus producing passages.

    See the module docstring: with a finite ``limit`` the caller is expected to
    have forced ``gold_doc_ids`` (via `plan_gold_coverage`) so the slice actually
    covers some golden queries instead of only distractors.
    """
    gold_doc_ids = set(gold_doc_ids or set())
    remaining_gold = set(gold_doc_ids)
    distractor_budget = None if limit is None else max(0, limit - len(gold_doc_ids))

    passages: list[Passage] = []
    audit = IngestAudit()
    doc_types: Counter[str] = Counter()
    char_lengths: list[int] = []
    distractors = 0

    for record in iter_corpus(settings, limit=None):
        is_gold = record.doc_id in remaining_gold
        if not is_gold:
            if distractor_budget is not None and distractors >= distractor_budget:
                # Budget spent; keep scanning only if gold documents are still missing.
                if not remaining_gold:
                    break
                continue
            distractors += 1
        else:
            remaining_gold.discard(record.doc_id)

        if not record.text.strip():
            audit.empty_text += 1

        doc_passages = chunk_document(record.doc_id, record.title, record.text, settings)
        passages.extend(doc_passages)

        audit.documents += 1
        meta = doc_passages[0].metadata
        if not meta.parse_ok:
            audit.metadata_parse_failures += 1
        doc_types[meta.doc_type or "unknown"] += 1
        if meta.year is not None:
            audit.year_min = meta.year if audit.year_min is None else min(audit.year_min, meta.year)
            audit.year_max = meta.year if audit.year_max is None else max(audit.year_max, meta.year)
        for passage in doc_passages:
            char_lengths.append(len(passage.embed_text))

    audit.passages = len(passages)
    audit.doc_type_counts = dict(doc_types.most_common())
    if char_lengths:
        audit.chars_mean = round(sum(char_lengths) / len(char_lengths), 1)
        audit.chars_p50 = _percentile(char_lengths, 50)
        audit.chars_p90 = _percentile(char_lengths, 90)
        audit.chars_p99 = _percentile(char_lengths, 99)
        audit.chars_max = max(char_lengths)
    audit.gold_documents_found = len(gold_doc_ids) - len(remaining_gold)
    audit.gold_documents_missing = sorted(remaining_gold)
    if remaining_gold:
        logger.warning("%d gold document ids were not found in the corpus.", len(remaining_gold))
    return passages, audit


def write_passages(settings: Settings, passages: list[Passage], audit: IngestAudit) -> Path:
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    path = settings.processed_dir / PASSAGES_FILE
    with path.open("w", encoding="utf-8") as handle:
        for passage in passages:
            handle.write(json.dumps(passage.model_dump(), ensure_ascii=False) + "\n")

    (settings.processed_dir / AUDIT_FILE).write_text(
        json.dumps(
            {
                "dataset_repo_id": settings.dataset_repo_id,
                "dataset_revision": settings.dataset_revision,
                "chunk_strategy": settings.chunk_strategy,
                **audit.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_passages(settings: Settings) -> list[Passage]:
    path = settings.processed_dir / PASSAGES_FILE
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `make ingest` first.")
    with path.open(encoding="utf-8") as handle:
        return [Passage.model_validate_json(line) for line in handle if line.strip()]
