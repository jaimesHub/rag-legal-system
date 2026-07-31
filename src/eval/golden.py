"""Build and load the golden dev/test splits, with a leakage guard.

``test`` (from qrels/test) is the evaluation and benchmark split for this
project (see CLAUDE.md "Bất biến" #1 and docs/plan.md §6) — no retriever here
trains on anything, so there is no tuning-then-final-check split to protect.
``dev`` (from qrels/train) is not used for retrieval evaluation; it is reserved
for later coursework that actually trains something (e.g. embedding fine-tuning),
where a held-out validation set matters.

**No leakage.** Some query ids appear in both train and test qrels. They are
removed from ``dev`` and kept in ``test`` (never the other way around), so
anything trained on ``dev`` later cannot have already seen a ``test`` query.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config.settings import Settings
from src.ingest.loader import load_qrels, load_queries
from src.schemas import GoldenExample, SplitStats

logger = logging.getLogger(__name__)

DEV_FILE = "dev.jsonl"
TEST_FILE = "test.jsonl"
MANIFEST_FILE = "manifest.json"


def _stats(name: str, examples: list[GoldenExample], excluded: int = 0) -> SplitStats:
    n_labels = sum(len(e.relevant_doc_ids) for e in examples)
    return SplitStats(
        name=name,
        n_queries=len(examples),
        n_labels=n_labels,
        mean_labels_per_query=round(n_labels / len(examples), 3) if examples else 0.0,
        multi_label_queries=sum(1 for e in examples if len(e.relevant_doc_ids) > 1),
        excluded_overlap=excluded,
    )


def _write(path: Path, examples: list[GoldenExample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example.model_dump(), ensure_ascii=False) + "\n")


def build_golden(settings: Settings) -> dict[str, SplitStats]:
    """Derive dev/test golden files from the pinned qrels."""
    queries, duplicate_rows = load_queries(settings)
    train = load_qrels(settings, "train")
    test = load_qrels(settings, "test")

    overlap = train.query_ids & test.query_ids
    if overlap:
        logger.warning(
            "Excluding %d query ids from dev: they also appear in the test qrels.",
            len(overlap),
        )

    def to_examples(labels: dict[str, dict[str, int]], skip: set[str]) -> list[GoldenExample]:
        out: list[GoldenExample] = []
        missing_text = 0
        for query_id, docs in sorted(labels.items()):
            if query_id in skip:
                continue
            query = queries.get(query_id)
            if query is None:
                missing_text += 1
                continue
            out.append(
                GoldenExample(
                    query_id=query_id,
                    text=query.text,
                    relevant_doc_ids=sorted(docs),
                    scores=dict(docs),
                )
            )
        if missing_text:
            logger.warning("%d labelled queries had no text in queries.jsonl.", missing_text)
        return out

    dev = to_examples(train.labels, skip=overlap)
    test_examples = to_examples(test.labels, skip=set())

    _write(settings.golden_dir / DEV_FILE, dev)
    _write(settings.golden_dir / TEST_FILE, test_examples)

    stats = {
        "dev": _stats("dev", dev, excluded=len(overlap)),
        "test": _stats("test", test_examples),
    }

    manifest = {
        "dataset_repo_id": settings.dataset_repo_id,
        "dataset_revision": settings.dataset_revision,
        "duplicate_query_rows_dropped": duplicate_rows,
        "overlap_query_ids_excluded_from_dev": sorted(overlap),
        "splits": {name: stat.model_dump() for name, stat in stats.items()},
        "note": (
            "test is the evaluation/benchmark split for this project. "
            "dev is not used for retrieval evaluation — reserved for later "
            "coursework that trains something (e.g. embedding fine-tuning)."
        ),
    }
    (settings.golden_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def load_golden(settings: Settings, split: str, *, limit: int | None = None) -> list[GoldenExample]:
    filename = {"dev": DEV_FILE, "test": TEST_FILE}.get(split)
    if filename is None:
        raise ValueError(f"split must be 'dev' or 'test', got {split!r}")

    path = settings.golden_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `make golden` first.")

    examples: list[GoldenExample] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            examples.append(GoldenExample.model_validate_json(line))
            if limit is not None and len(examples) >= limit:
                break
    return examples
