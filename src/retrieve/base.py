"""Shared retriever contract: `Retriever.retrieve(query, k) -> list[SearchHit]`.

# Phase 2/3 (docs/t0.md step 12): `SearchHit` (doc_id, score, passage_id,
# title, text, metadata) and `dedupe_by_doc` (collapse multiple passages of
# the same Điều to its highest-scoring hit). Stub only for Phase 1 — no
# logic yet.
"""

from __future__ import annotations
