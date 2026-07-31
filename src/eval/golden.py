"""Build dev/test golden splits from queries + qrels, with a leakage guard.

# Phase 2 (docs/t0.md step 9): `build_golden(settings)` — dedupe queries by
# _id, compute train/test query-id overlap, drop overlapping ids from dev
# (never from test), write data/golden/{dev,test}.jsonl + manifest.json.
# `load_golden(settings, split)` reads them back. Stub only for Phase 1 —
# no logic yet.
"""

from __future__ import annotations
