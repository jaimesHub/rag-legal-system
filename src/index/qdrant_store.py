"""Qdrant collection wrapper — named dense vector, deterministic point ids.

# Phase 2 (docs/t0.md step 11): `QdrantStore` with `ensure_collection`,
# `upsert` (UUID5 from passage_id so re-running upserts, never duplicates),
# `search`, `count`, `collection_info`, `iter_payloads`. Payload index for
# T5 filter fields (doc_id, doc_key, doc_type, issuer, year) created up
# front even though nothing filters on them yet. Stub only for Phase 1 —
# no logic yet.
"""

from __future__ import annotations
