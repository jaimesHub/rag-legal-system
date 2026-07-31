"""Parse corpus ids and titles into `src.schemas.LegalMetadata`.

# Phase 2 (docs/t0.md step 8): `parse_corpus_id` (doc_key/article_index ->
# number/year/code -> doc_type/issuer, defensive with parse_ok=False on
# mismatch) and `parse_title` (Điều number + heading). Stub only for
# Phase 1 — no logic yet.
"""

from __future__ import annotations
