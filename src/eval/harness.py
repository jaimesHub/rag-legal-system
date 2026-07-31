"""Per-query evaluation harness: run a retriever over golden examples, report metrics + latency.

# Phase 2 (docs/t0.md step 13): `evaluate_retriever(retriever, examples, ks,
# split, ...)` -> `EvalReport` (metrics, latency mean/p50/p95, failures,
# per_query, provenance context); `save_report`/`load_report`/
# `list_reports` under artifacts/eval/. Stub only for Phase 1 — no logic
# yet.
"""

from __future__ import annotations
