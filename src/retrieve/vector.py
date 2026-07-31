"""Dense vector retriever backed by `src.index.qdrant_store.QdrantStore`.

# Phase 2/3 (docs/t0.md step 12): `VectorRetriever` — embeds the query with
# task_type="RETRIEVAL_QUERY" (asymmetric vs. RETRIEVAL_DOCUMENT at index
# time), oversamples k*3 before `dedupe_by_doc` so top-k isn't dominated by
# one document's passages. Stub only for Phase 1 — no logic yet.
"""

from __future__ import annotations
