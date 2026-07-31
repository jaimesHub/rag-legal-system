"""Build the gold-covering passage slice used by `make ingest` / smoke test.

# Phase 2 (docs/t0.md step 10): `build_passages(settings, limit,
# gold_doc_ids)` — streams the corpus, chunks each record, forces gold
# documents into the slice before filling the rest with distractors
# (`plan_gold_coverage`), and writes `data/processed/passages.jsonl` +
# `ingest_audit.json`. Numbers from this slice are optimistic by design.
# Stub only for Phase 1 — no logic yet.
"""

from __future__ import annotations
