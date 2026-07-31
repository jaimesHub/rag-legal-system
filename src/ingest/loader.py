"""Download the raw dataset from Hugging Face and verify it against docs/plan.md §1b.

We read the raw JSONL directly rather than going through the `datasets`/MTEB parquet
config: the raw files carry both train and test qrels, while the MTEB config only
exposes the test split, and the raw files use the BEIR key `_id` where the parquet
config uses `id` — every loader here accepts both. The revision is pinned in
`config.settings` so the benchmark can never silently drift.

Verified schema (Phase 2 real run, revision 12d76d4d — see EXPECTED below for the
exact counts observed; if a future re-run disagrees, the pin has moved).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from huggingface_hub import hf_hub_download

from config.settings import Settings
from src.schemas import Query

logger = logging.getLogger(__name__)

CORPUS_FILE = "corpus.jsonl"
QUERIES_FILE = "queries.jsonl"
QRELS_TRAIN_FILE = "qrels/train.jsonl"
QRELS_TEST_FILE = "qrels/test.jsonl"

ALL_FILES = (CORPUS_FILE, QUERIES_FILE, QRELS_TRAIN_FILE, QRELS_TEST_FILE)

# Asserted by `verify_dataset`. These are the REAL counts observed from the first
# full download at dataset_revision=12d76d4d04b94ceada970fcfbe7fec20bfa97389
# (Phase 2, docs/t0.md step 7) — not guessed. A future mismatch means the pinned
# revision moved or a download was truncated.
EXPECTED = {
    "corpus_records": 61425,
    "query_rows": 3298,
    "unique_queries": 3196,
    "qrels_train_labels": 2505,
    "qrels_test_labels": 793,
    "train_queries": 2432,
    "test_queries": 788,
    "overlap_queries": 24,
}


@dataclass
class CorpusRecord:
    doc_id: str
    title: str
    text: str


@dataclass
class QrelSet:
    """query_id -> {doc_id: score}."""

    name: str
    labels: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def n_labels(self) -> int:
        return sum(len(v) for v in self.labels.values())

    @property
    def query_ids(self) -> set[str]:
        return set(self.labels)


def _download(settings: Settings, filename: str) -> Path:
    """Fetch one dataset file into data/raw/, or return the cached copy.

    Every loader goes through here, so no command needs an explicit download
    step: the first call that needs data fetches it, later calls reuse the
    cache hf_hub_download keeps under data/raw/.
    """
    return Path(
        hf_hub_download(
            repo_id=settings.dataset_repo_id,
            filename=filename,
            repo_type="dataset",
            revision=settings.dataset_revision,
            local_dir=settings.raw_dir,
        )
    )


def download_file(settings: Settings, filename: str) -> Path:
    """Public wrapper: fetch one dataset file, or return the cached copy."""
    return _download(settings, filename)


def download_all(settings: Settings) -> list[tuple[str, Path, int]]:
    """Pre-fetch every dataset file. Returns (filename, path, bytes) per file."""
    out: list[tuple[str, Path, int]] = []
    for filename in ALL_FILES:
        path = _download(settings, filename)
        out.append((filename, path, path.stat().st_size))
    return out


def _read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSON at %s:%d", path.name, line_no)


def _identifier(row: dict) -> str | None:
    """Raw JSONL uses BEIR's ``_id``; the parquet configs use ``id`` — accept both."""
    value = row.get("_id") or row.get("id")
    return str(value) if value is not None else None


def iter_corpus(settings: Settings, limit: int | None = None) -> Iterator[CorpusRecord]:
    """Stream corpus records (the file is ~100+ MB, so streaming is the default)."""
    path = _download(settings, CORPUS_FILE)
    emitted = 0
    for row in _read_jsonl(path):
        doc_id = _identifier(row)
        if doc_id is None:
            continue
        yield CorpusRecord(doc_id=doc_id, title=row.get("title") or "", text=row.get("text") or "")
        emitted += 1
        if limit is not None and emitted >= limit:
            return


def count_corpus(settings: Settings) -> int:
    """Total corpus records, used by `verify_dataset`."""
    return sum(1 for _ in iter_corpus(settings, limit=None))


def load_queries(settings: Settings) -> tuple[dict[str, Query], int]:
    """Return unique queries by id, plus the number of duplicate rows dropped.

    queries.jsonl ships duplicate `_id` rows; loading naively into a list would
    double-count those queries in every metric downstream.
    """
    path = _download(settings, QUERIES_FILE)
    queries: dict[str, Query] = {}
    duplicates = 0
    for row in _read_jsonl(path):
        query_id = _identifier(row)
        text = row.get("text") or ""
        if query_id is None:
            continue
        if query_id in queries:
            duplicates += 1
            continue
        queries[query_id] = Query(query_id=query_id, text=text)
    if duplicates:
        logger.info("Dropped %d duplicate query rows (kept first occurrence).", duplicates)
    return queries, duplicates


def load_qrels(settings: Settings, split: str) -> QrelSet:
    """Load train or test qrels into query_id -> {doc_id: score}."""
    filename = {"train": QRELS_TRAIN_FILE, "test": QRELS_TEST_FILE}.get(split)
    if filename is None:
        raise ValueError(f"split must be 'train' or 'test', got {split!r}")

    path = _download(settings, filename)
    qrels = QrelSet(name=split)
    for row in _read_jsonl(path):
        query_id = row.get("query-id")
        doc_id = row.get("corpus-id")
        if query_id is None or doc_id is None:
            continue
        # Scores arrive as int in qrels/*.jsonl and float in some configs.
        score = int(float(row.get("score", 1)))
        qrels.labels.setdefault(str(query_id), {})[str(doc_id)] = score
    return qrels


def verify_dataset(settings: Settings) -> dict[str, object]:
    """Download the pinned dataset and compare observed counts against EXPECTED.

    Returns a dict with the expected-vs-observed table plus the two extra audit
    numbers t0.md step 7 asks for: duplicate `_id` rows in queries.jsonl, and the
    count of query ids overlapping between train/test qrels.
    """
    n_corpus = count_corpus(settings)
    queries, duplicates = load_queries(settings)
    train = load_qrels(settings, "train")
    test = load_qrels(settings, "test")
    overlap = train.query_ids & test.query_ids

    observed = {
        "corpus_records": n_corpus,
        "unique_queries": len(queries),
        "query_rows": len(queries) + duplicates,
        "qrels_train_labels": train.n_labels,
        "qrels_test_labels": test.n_labels,
        "train_queries": len(train.query_ids),
        "test_queries": len(test.query_ids),
        "overlap_queries": len(overlap),
    }

    checks = []
    for key, expected in EXPECTED.items():
        actual = observed.get(key)
        checks.append(
            {"check": key, "expected": expected, "observed": actual, "ok": actual == expected}
        )

    return {
        "dataset_repo_id": settings.dataset_repo_id,
        "dataset_revision": settings.dataset_revision,
        "checks": checks,
        "duplicate_query_rows": duplicates,
        "overlap_query_ids": sorted(overlap),
        "overlap_count": len(overlap),
        "all_ok": all(c["ok"] for c in checks),
    }
