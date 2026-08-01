"""Offline tests for the cross-project comparator (src/eval/compare_sample.py).

The load-bearing behaviour is the same-config guard: metric comparison must be
refused unless the current run is the real full-corpus 788-test benchmark on the
pinned revision — exactly the invariant compare.py enforces within a project.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.eval import compare_sample as cs
from src.eval.harness import EvalReport

PIN = "12d76d4d04b94ceada970fcfbe7fec20bfa97389"
REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ROOT = REPO_ROOT.parent / "aie-rag-sample-project"

META = {
    "benchmark_split": "test",
    "dataset_revision": PIN,
    "benchmark_n_queries": 788,
    "full_corpus_documents": 61425,
}
T2_ENTRY = {
    "status": "done",
    "metric_comparable": True,
    "variants": [
        {
            "label": "bm25-underthesea",
            "canonical": True,
            "metrics": {"recall@10": 0.8610, "mrr@10": 0.5785},
        }
    ],
}
T3_ENTRY = {"status": "todo", "metric_comparable": False, "reason": "Sample chưa công bố T3."}


def _report(
    *,
    split: str = "test",
    n_queries: int = 788,
    n_documents: int = 61425,
    revision: str = PIN,
    metrics: dict | None = None,
) -> EvalReport:
    return EvalReport(
        retriever="bm25",
        split=split,
        n_queries=n_queries,
        ks=[1, 5, 10],
        metrics=metrics or {"recall@10": 0.83, "mrr@10": 0.55},
        latency_ms={"mean": 1.0, "p50": 1.0, "p95": 1.18},
        context={"dataset_revision": revision, "n_documents": n_documents},
    )


# --- same-config guard -------------------------------------------------------
def test_guard_passes_on_full_corpus_788_test():
    comparable, reasons = cs.metric_guard(_report(), META, T2_ENTRY, week=2)
    assert comparable is True
    assert reasons == []


def test_guard_refuses_wrong_split():
    comparable, reasons = cs.metric_guard(_report(split="dev"), META, T2_ENTRY, week=2)
    assert comparable is False
    assert any("split" in r for r in reasons)


def test_guard_refuses_slice_not_full_corpus():
    # The exact shape of the T0 fake tripwire: 573 queries, 500-doc slice.
    comparable, reasons = cs.metric_guard(
        _report(n_queries=573, n_documents=500), META, T2_ENTRY, week=2
    )
    assert comparable is False
    assert any("n_queries" in r for r in reasons)
    assert any("n_documents" in r for r in reasons)


def test_guard_refuses_revision_mismatch():
    comparable, reasons = cs.metric_guard(_report(revision="deadbeef"), META, T2_ENTRY, week=2)
    assert comparable is False
    assert any("dataset_revision" in r for r in reasons)


def test_guard_refuses_when_sample_has_no_baseline():
    comparable, reasons = cs.metric_guard(_report(), META, T3_ENTRY, week=3)
    assert comparable is False
    assert any("T3" in r or "chưa" in r for r in reasons)


def test_guard_refuses_when_no_current_report():
    comparable, reasons = cs.metric_guard(None, META, T2_ENTRY, week=2)
    assert comparable is False
    assert any("run" in r.lower() for r in reasons)


# --- metric block ------------------------------------------------------------
def test_metric_block_computes_delta_and_beats_flag_false():
    block = cs.build_metric_block(
        _report(metrics={"recall@10": 0.83, "mrr@10": 0.55}), META, T2_ENTRY, 2
    )
    assert block["comparable"] is True
    assert block["delta"]["recall@10"] == pytest.approx(0.83 - 0.8610, abs=1e-6)
    assert block["beats_sample"] is False
    assert block["sample_label"] == "bm25-underthesea"


def test_metric_block_beats_sample_true():
    block = cs.build_metric_block(_report(metrics={"recall@10": 0.90}), META, T2_ENTRY, 2)
    assert block["comparable"] is True
    assert block["beats_sample"] is True


def test_metric_block_not_comparable_returns_reasons():
    block = cs.build_metric_block(_report(split="dev"), META, T2_ENTRY, 2)
    assert block["comparable"] is False
    assert block["reasons"]


# --- own-bar (decision 3): current run alone qualifies axis 3 ---------------
def test_current_run_qualifies_true_for_full_corpus_788_test():
    assert cs.current_run_qualifies(_report(), META) is True


def test_current_run_qualifies_false_for_t0_slice_shape():
    # Same slice shape the guard test above uses: 573 queries, 500-doc slice.
    assert cs.current_run_qualifies(_report(n_queries=573, n_documents=500), META) is False


def test_current_run_qualifies_false_for_wrong_split():
    assert cs.current_run_qualifies(_report(split="dev"), META) is False


def test_current_run_qualifies_false_for_no_report():
    assert cs.current_run_qualifies(None, META) is False


def _min_snap() -> dict:
    return {
        "src_files": 1,
        "test_files": 1,
        "test_functions": 1,
        "failure_entries": 1,
        "modules": {},
    }


def test_build_scorecard_axis3_own_bar_when_sample_not_comparable():
    # Week 3: sample has no baseline (metric_comparable: false) but THIS project
    # has a real full-corpus 788-test run -> own-bar pass, per decision 3.
    report = _report()
    metric_block = cs.build_metric_block(report, META, T3_ENTRY, 3)
    assert metric_block["comparable"] is False  # sample side still refuses head-to-head
    axes = cs.build_scorecard(3, REPO_ROOT, _min_snap(), _min_snap(), metric_block, report, META)
    assert axes["3. metrics"]["status"] == cs.OK
    assert "own-bar" in axes["3. metrics"]["evidence"]


def test_build_scorecard_axis3_na_for_t0_slice_report_on_week3():
    # The T0 tripwire shape must NOT qualify for own-bar on any week.
    report = _report(n_queries=573, n_documents=500)
    metric_block = cs.build_metric_block(report, META, T3_ENTRY, 3)
    axes = cs.build_scorecard(3, REPO_ROOT, _min_snap(), _min_snap(), metric_block, report, META)
    assert axes["3. metrics"]["status"] == cs.NA


# --- structural snapshot -----------------------------------------------------
def test_structural_snapshot_current_scope():
    snap = cs.structural_snapshot(REPO_ROOT)
    mods = snap["modules"]
    assert mods["src/retrieve/vector.py"] is True  # exists since T0
    assert mods["src/eval/compare_sample.py"] is True  # this feature
    assert mods["src/retrieve/bm25.py"] is False  # T2, not built yet
    assert mods["src/ingest/tokenize.py"] is False  # T2, not built yet
    assert mods["src/retrieve/hybrid.py"] is False  # T4, not built yet
    assert mods["src/retrieve/metadata.py"] is False  # T5, not built yet
    assert snap["cli_commands"] > 0
    assert snap["test_functions"] > 0


@pytest.mark.skipif(not SAMPLE_ROOT.exists(), reason="sample project not present")
def test_structural_snapshot_sample_is_broader():
    cur = cs.structural_snapshot(REPO_ROOT)
    smp = cs.structural_snapshot(SAMPLE_ROOT)
    assert smp["modules"]["src/retrieve/bm25.py"] is True  # sample did T2
    assert smp["src_files"] > cur["src_files"]  # sample implements more weeks


# --- failure-log counting ----------------------------------------------------
def test_count_failure_entries_for_week_t0():
    # This project logged multiple T0 failure cases (F-001.., F-012/13 tagged T0).
    n = cs.count_failure_entries_for_week(REPO_ROOT / "failure_log.md", 0)
    assert n >= 3


def test_count_failure_entries_missing_file(tmp_path):
    assert cs.count_failure_entries_for_week(tmp_path / "nope.md", 2) == 0


# --- retriever family matching (names embed config, e.g. vector[fake-embedding@768]) ---
def test_retriever_matches_bracketed_name():
    assert cs._retriever_matches("vector[fake-embedding@768]", "vector") is True
    assert cs._retriever_matches("bm25[underthesea,k1=1.5]", "bm25") is True
    assert cs._retriever_matches("vector[fake-embedding@768]", "bm25") is False


# --- markdown emitter --------------------------------------------------------
def _result(metric_block: dict, week: int = 2) -> dict:
    axes = {
        "1. structure": {"status": cs.OK, "evidence": "…"},
        "2. tests": {"status": cs.PARTIAL, "evidence": "…"},
        "3. metrics": {
            "status": cs.OK if metric_block.get("comparable") else cs.NA,
            "evidence": "…",
        },
        "4. docs": {"status": cs.OK, "evidence": "…"},
        "5. failure-log": {"status": cs.OK, "evidence": "…"},
        "6. reproducibility": {"status": cs.OK, "evidence": "…"},
        "7. git": {"status": cs.PARTIAL, "evidence": "…"},
    }
    return {
        "week": week,
        "retriever": "bm25",
        "structural": {
            "current": {
                "src_files": 1,
                "cli_commands": 1,
                "make_targets": 1,
                "test_functions": 1,
                "failure_entries": 1,
            },
            "sample": {
                "src_files": 1,
                "cli_commands": 1,
                "make_targets": 1,
                "test_functions": 1,
                "failure_entries": 1,
            },
        },
        "metric": metric_block,
        "axes": axes,
        "overall": "on-track",
    }


def test_to_markdown_has_scorecard_and_metric_table_when_comparable():
    block = cs.build_metric_block(_report(), META, T2_ENTRY, 2)
    md = cs.to_markdown(_result(block))
    assert "## So với dự án mẫu (T2)" in md
    assert "Scorecard 7 trục" in md
    assert "recall@10" in md
    assert "Metric (cùng cấu hình)" in md


def test_to_markdown_shows_dash_line_when_not_comparable():
    block = cs.build_metric_block(_report(split="dev"), META, T2_ENTRY, 2)
    md = cs.to_markdown(_result(block))
    assert "➖ Chưa so được metric" in md
