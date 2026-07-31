"""Download the raw dataset from Hugging Face and verify it against docs/plan.md §1b.

# Phase 2 (docs/t0.md step 7): `_download` (hf_hub_download, revision-pinned),
# `EXPECTED` constants, and the `verify-dataset` CLI command that checks
# corpus/queries/qrels counts + train/test query-id leakage + duplicate
# `_id` rows in queries.jsonl. Stub only for Phase 1 — no logic yet.
"""

from __future__ import annotations
