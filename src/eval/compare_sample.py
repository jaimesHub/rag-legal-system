"""Compare THIS project against the SAMPLE reference project, week by week (T0..T8).

Holistic scorecard on 7 axes (structure / tests / metrics / docs / failure-log /
reproducibility / git), plus a same-config metric guard so head-to-head numbers are
only shown when both sides ran the identical benchmark (revision + split=test +
788 queries + full 61,425-doc corpus). See docs/comparison-framework.md.

Design decisions baked in (from the approved plan):
- The sample's real numbers come from a human-curated YAML (docs/sample-baselines.yaml),
  never invented, because the sample's eval artifacts are gitignored.
- The metric bar is "a real reproducible number + per-query explanation exists" — NOT
  "beat the sample". Beating the sample is reported as a bonus flag, never a gate.
- This is a scorecard aid, not a build gate: the CLI always exits 0.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

from src.eval.harness import EvalReport, list_reports, load_report

# --- status vocabulary -------------------------------------------------------
OK = "✅"  # on-track vs reference
PARTIAL = "🟡"  # partial / needs manual confirmation
BEHIND = "🔴"  # behind
NA = "➖"  # not applicable this week

# Milestone paths whose presence signals scope progress; reported for both repos.
# A trailing-less path with a dot is a file; otherwise a directory.
MILESTONE_PATHS = [
    "src/retrieve/vector.py",
    "src/retrieve/bm25.py",
    "src/retrieve/splade.py",
    "src/retrieve/hybrid.py",
    "src/retrieve/metadata.py",
    "src/ingest/tokenize.py",
    "src/eval/compare.py",
    "src/eval/compare_sample.py",
    "src/rank",
    "src/generate",
    "src/graph",
    "src/parse",
    "dashboard",
    "notebooks",
]

# Modules THIS project is expected to have by the end of each week. Empty = no new
# required module that week (kept conservative; extend as weeks are scoped).
WEEK_EXPECTED_MODULES: dict[int, list[str]] = {
    0: [],
    1: ["src/eval/compare.py"],
    2: ["src/retrieve/bm25.py", "src/ingest/tokenize.py", "src/eval/compare.py"],
    3: [],  # vector retriever already exists since T0; T3 is ingestion polish
    # Hybrid/metadata module names below are the expected T4/T5 paths per docs/plan.md
    # §2/§5; realign here if the real module names differ once those weeks land.
    4: ["src/rank", "src/retrieve/hybrid.py"],
    5: ["src/retrieve/metadata.py"],
    6: ["src/graph"],
    7: ["src/parse"],
    8: ["dashboard"],
}

# Default retriever whose test-split report anchors the metric comparison, per week.
WEEK_RETRIEVER: dict[int, str] = {
    0: "vector",
    1: "vector",
    2: "bm25",
    3: "vector",
    4: "hybrid",
    5: "hybrid",
    6: "vector",
    7: "vector",
    8: "hybrid",
}


# --- loading -----------------------------------------------------------------
def load_sample_baselines(path: Path) -> dict[str, Any]:
    """Load the curated sample-baselines YAML (meta + weeks)."""
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def week_entry(baselines: dict[str, Any], week: int) -> dict[str, Any] | None:
    return (baselines.get("weeks") or {}).get(f"T{week}")


# --- structural snapshot -----------------------------------------------------
def _exists(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def _count_pattern(path: Path, needle: str) -> int:
    if not path.exists():
        return 0
    return path.read_text(encoding="utf-8", errors="ignore").count(needle)


def _count_make_targets(makefile: Path) -> int:
    if not makefile.exists():
        return 0
    n = 0
    for line in makefile.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        # help-annotated target: `name: ... ## description`
        if "##" in stripped and ":" in stripped.split("##", 1)[0]:
            head = stripped.split(":", 1)[0]
            if head and all(c.isalnum() or c in "_-" for c in head):
                n += 1
    return n


def _count_test_functions(tests_dir: Path) -> tuple[int, int]:
    """(number of test_*.py files, number of `def test_` functions)."""
    if not tests_dir.exists():
        return 0, 0
    files = [p for p in tests_dir.rglob("test_*.py") if "__pycache__" not in p.parts]
    funcs = sum(_count_pattern(p, "def test_") for p in files)
    return len(files), funcs


def _count_failure_entries(failure_log: Path) -> int:
    if not failure_log.exists():
        return 0
    return sum(
        1
        for line in failure_log.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.startswith("## F-")
    )


def structural_snapshot(root: Path) -> dict[str, Any]:
    """Filesystem-only scope signals for one repo. Always available (offline)."""
    src = root / "src"
    src_files = (
        len([p for p in src.rglob("*.py") if "__pycache__" not in p.parts]) if src.exists() else 0
    )
    test_files, test_functions = _count_test_functions(root / "tests")
    return {
        "src_files": src_files,
        "cli_commands": _count_pattern(root / "src" / "cli.py", "@app.command"),
        "make_targets": _count_make_targets(root / "Makefile"),
        "test_files": test_files,
        "test_functions": test_functions,
        "failure_entries": _count_failure_entries(root / "failure_log.md"),
        "modules": {rel: _exists(root, rel) for rel in MILESTONE_PATHS},
    }


def count_failure_entries_for_week(failure_log: Path, week: int) -> int:
    """Entries tagged for this week, e.g. `**Tuần:** T2` (also matches `T0 (Phase 4)`)."""
    if not failure_log.exists():
        return 0
    text = failure_log.read_text(encoding="utf-8", errors="ignore")
    marker = f"**Tuần:** T{week}"
    count = 0
    for line in text.splitlines():
        idx = line.find(marker)
        if idx == -1:
            continue
        after = line[idx + len(marker) : idx + len(marker) + 1]
        # avoid T2 matching T20+ ; the next char must not be a digit
        if not after.isdigit():
            count += 1
    return count


# --- current report discovery ------------------------------------------------
def _retriever_matches(report_retriever: str, wanted: str) -> bool:
    # Retriever names embed their config, e.g. "vector[fake-embedding@768]" or
    # "bm25[underthesea,k1=1.5]". Match on the family before the bracket.
    family = report_retriever.split("[", 1)[0].strip()
    return family == wanted or family.split("-", 1)[0] == wanted


def find_current_report(eval_dir: Path, retriever: str, split: str = "test") -> EvalReport | None:
    """Newest report for the given retriever on the given split, or None."""
    if not eval_dir.exists():
        return None
    candidates: list[EvalReport] = []
    for path in list_reports(eval_dir):
        try:
            report = load_report(path)
        except Exception:
            continue
        if report.split == split and _retriever_matches(report.retriever, retriever):
            candidates.append(report)
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.created_at)


# --- same-config metric guard ------------------------------------------------
def metric_guard(
    report: EvalReport | None,
    meta: dict[str, Any],
    entry: dict[str, Any] | None,
    week: int,
) -> tuple[bool, list[str]]:
    """Return (comparable, reasons). Comparable only when EVERY check passes."""
    reasons: list[str] = []
    if entry is None:
        reasons.append(f"sample-baselines.yaml không có mục T{week}.")
        return False, reasons
    if not entry.get("metric_comparable"):
        reasons.append(entry.get("reason") or f"Sample chưa có số so được cho T{week}.")
        return False, reasons
    if report is None:
        reasons.append("Chưa có run test hiện tại cho retriever của tuần này.")
        return False, reasons

    ctx = report.context or {}
    if report.split != meta.get("benchmark_split", "test"):
        reasons.append(f"split={report.split!r}, không phải {meta.get('benchmark_split')!r}.")
    if ctx.get("dataset_revision") != meta.get("dataset_revision"):
        reasons.append("dataset_revision không khớp pin của mẫu.")
    if report.n_queries != meta.get("benchmark_n_queries"):
        reasons.append(
            f"n_queries={report.n_queries}, không phải {meta.get('benchmark_n_queries')} "
            "(run là slice, không phải full test)."
        )
    if ctx.get("n_documents") != meta.get("full_corpus_documents"):
        reasons.append(
            f"n_documents={ctx.get('n_documents')}, không phải "
            f"{meta.get('full_corpus_documents')} (không phải full corpus)."
        )
    return (not reasons), reasons


def current_run_qualifies(report: EvalReport | None, meta: dict[str, Any]) -> bool:
    """The current run is itself a real full-corpus 788-test run on the pin —
    enough to PASS on own-bar even when the sample has no baseline (decision 3).
    """
    if report is None:
        return False
    ctx = report.context or {}
    return (
        report.split == meta.get("benchmark_split", "test")
        and ctx.get("dataset_revision") == meta.get("dataset_revision")
        and report.n_queries == meta.get("benchmark_n_queries")
        and ctx.get("n_documents") == meta.get("full_corpus_documents")
    )


def canonical_variant(entry: dict[str, Any]) -> dict[str, Any] | None:
    variants = entry.get("variants") or []
    if not variants:
        return None
    for v in variants:
        if v.get("canonical"):
            return v
    return variants[0]


def build_metric_block(
    report: EvalReport | None,
    meta: dict[str, Any],
    entry: dict[str, Any] | None,
    week: int,
) -> dict[str, Any]:
    comparable, reasons = metric_guard(report, meta, entry, week)
    block: dict[str, Any] = {"comparable": comparable, "reasons": reasons}
    if not comparable or report is None or entry is None:
        return block

    variant = canonical_variant(entry)
    if variant is None:
        block["comparable"] = False
        block["reasons"] = ["Sample entry không có `variants` để so."]
        return block

    sample_metrics = variant.get("metrics", {})
    current = {m: report.metrics[m] for m in sample_metrics if m in report.metrics}
    delta = {m: round(current[m] - sample_metrics[m], 4) for m in current}
    block.update(
        {
            "sample_label": variant.get("label", "sample"),
            "sample": sample_metrics,
            "current": current,
            "delta": delta,
            "beats_sample": (
                current.get("recall@10", 0.0) >= sample_metrics.get("recall@10", 1.0)
                if "recall@10" in current
                else None
            ),
        }
    )
    return block


# --- scorecard ---------------------------------------------------------------
def _git_week_commits(root: Path, week: int) -> int:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--oneline"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if out.returncode != 0:
        return 0
    low = out.stdout.lower()
    return sum(1 for ln in low.splitlines() if f"week{week}" in ln or f"t{week}" in ln)


def build_scorecard(
    week: int,
    current_root: Path,
    current_snap: dict[str, Any],
    sample_snap: dict[str, Any],
    metric_block: dict[str, Any],
    report: EvalReport | None,
    meta: dict[str, Any],
) -> dict[str, dict[str, str]]:
    axes: dict[str, dict[str, str]] = {}

    # 1. structure / scope
    expected = WEEK_EXPECTED_MODULES.get(week, [])
    missing = [m for m in expected if not current_snap["modules"].get(m)]
    sample_extra = [
        m
        for m, present in sample_snap["modules"].items()
        if present and not current_snap["modules"].get(m)
    ]
    axes["1. structure"] = {
        "status": OK if not missing else PARTIAL,
        "evidence": (
            f"src {current_snap['src_files']} files vs mẫu {sample_snap['src_files']}; "
            f"thiếu module tuần: {missing or '—'}; mẫu có thêm: {sample_extra or '—'}"
        ),
    }

    # 2. test coverage (count auto; green must be confirmed by `make test`)
    axes["2. tests"] = {
        "status": PARTIAL,
        "evidence": (
            f"{current_snap['test_files']} files / {current_snap['test_functions']} funcs "
            f"(mẫu {sample_snap['test_files']}/{sample_snap['test_functions']}); "
            "chạy `make test` để xác nhận xanh"
        ),
    }

    # 3. metrics / benchmark rigor
    if metric_block.get("comparable"):
        delta = metric_block.get("delta", {})
        beats = metric_block.get("beats_sample")
        tag = "≥ mẫu (bonus)" if beats else "có số thật (đạt)"
        axes["3. metrics"] = {
            "status": OK,
            "evidence": f"so được vs {metric_block.get('sample_label')}; Δ={delta}; {tag}",
        }
    elif report is not None and current_run_qualifies(report, meta):
        axes["3. metrics"] = {
            "status": OK,
            "evidence": "own-bar: có số thật full-corpus 788-test (mẫu chưa có số) — đạt",
        }
    elif report is None:
        axes["3. metrics"] = {"status": NA, "evidence": "chưa có run test hiện tại"}
    else:
        axes["3. metrics"] = {
            "status": NA,
            "evidence": (metric_block.get("reasons") or ["không so được"])[0],
        }

    # 4. docs
    report_md = current_root / "reports" / f"week{week}.md"
    if report_md.exists():
        has_section = "So với dự án mẫu" in report_md.read_text(encoding="utf-8", errors="ignore")
        axes["4. docs"] = {
            "status": OK if has_section else PARTIAL,
            "evidence": (
                f"reports/week{week}.md có"
                + (
                    " + mục 'So với dự án mẫu'"
                    if has_section
                    else " (thiếu mục 'So với dự án mẫu')"
                )
            ),
        }
    else:
        axes["4. docs"] = {"status": BEHIND, "evidence": f"thiếu reports/week{week}.md"}

    # 5. failure-log
    new_entries = count_failure_entries_for_week(current_root / "failure_log.md", week)
    axes["5. failure-log"] = {
        "status": OK if new_entries >= 3 else (PARTIAL if new_entries else BEHIND),
        "evidence": f"{new_entries} entry gắn T{week} (yêu cầu ≥3/tuần)",
    }

    # 6. reproducibility
    ctx = (report.context if report else {}) or {}
    revision_ok = ctx.get("dataset_revision") == meta.get("dataset_revision")
    axes["6. reproducibility"] = {
        "status": OK if (report and revision_ok) else PARTIAL,
        "evidence": (
            "context có provenance, revision khớp pin"
            if (report and revision_ok)
            else "chưa có report hoặc revision chưa khớp"
        ),
    }

    # 7. git cadence
    commits = _git_week_commits(current_root, week)
    axes["7. git"] = {
        "status": PARTIAL,
        "evidence": f"{commits} commit nhắc tới T{week}/week{week}",
    }
    return axes


def overall_status(axes: dict[str, dict[str, str]]) -> str:
    crisp = [axes[a]["status"] for a in ("1. structure", "3. metrics", "5. failure-log")]
    if BEHIND in crisp:
        return "behind"
    if all(s in (OK, NA) for s in crisp):
        return "on-track"
    return "review"


# --- orchestrator ------------------------------------------------------------
def compare_sample(
    *,
    week: int,
    current_root: Path,
    sample_root: Path,
    baselines_path: Path,
    eval_dir: Path,
    retriever: str | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Full comparison result (structural + metric guard + scorecard), serializable."""
    baselines = load_sample_baselines(baselines_path)
    meta = baselines.get("meta", {})
    entry = week_entry(baselines, week)
    retr = retriever or WEEK_RETRIEVER.get(week, "vector")

    if report_path is not None:
        report: EvalReport | None = load_report(report_path)
    else:
        report = find_current_report(eval_dir, retr, split=meta.get("benchmark_split", "test"))

    current_snap = structural_snapshot(current_root)
    sample_snap = structural_snapshot(sample_root)
    metric_block = build_metric_block(report, meta, entry, week)
    axes = build_scorecard(
        week, current_root, current_snap, sample_snap, metric_block, report, meta
    )
    return {
        "week": week,
        "retriever": retr,
        "sample_commit": meta.get("sample_commit"),
        "dataset_revision": meta.get("dataset_revision"),
        "report_run_id": report.run_id if report else None,
        "report_label": report.label if report else None,
        "structural": {"current": current_snap, "sample": sample_snap},
        "metric": metric_block,
        "axes": axes,
        "overall": overall_status(axes),
    }


# --- rendering ---------------------------------------------------------------
def to_markdown(result: dict[str, Any]) -> str:
    """The 'So với dự án mẫu (T{N})' section, ready to paste into reports/weekN.md."""
    week = result["week"]
    axes = result["axes"]
    lines = [
        f"## So với dự án mẫu (T{week})",
        "",
        "> Nguồn số mẫu: `docs/sample-baselines.yaml` (chép tay từ report đã commit của mẫu).",
        "> Hàng metric chỉ hiện khi cùng cấu hình (revision + split=test + full corpus + 788 câu);",
        "> nếu không, đánh ➖ kèm lý do. Không bịa số.",
        "",
        "### Scorecard 7 trục",
        "",
        "| Trục | Trạng thái | Bằng chứng |",
        "|------|:----------:|------------|",
    ]
    for name, axis in axes.items():
        lines.append(f"| {name} | {axis['status']} | {axis['evidence']} |")
    lines.append("")

    metric = result["metric"]
    if metric.get("comparable"):
        lines += [
            "### Metric (cùng cấu hình)",
            "",
            f"| metric | current | sample ({metric['sample_label']}) | Δ |",
            "|--------|--------:|--------:|--:|",
        ]
        for m in sorted(metric["current"]):
            lines.append(
                f"| {m} | {metric['current'][m]:.4f} | {metric['sample'][m]:.4f} "
                f"| {metric['delta'][m]:+.4f} |"
            )
        bonus = (
            "≥ mẫu (bonus)"
            if metric.get("beats_sample")
            else "chưa vượt mẫu (không sao — không phải cửa)"
        )
        lines += ["", f"**Bar (quyết định 3):** có số thật + giải thích per-query = ĐẠT. {bonus}."]
    else:
        reason = (metric.get("reasons") or ["không so được"])[0]
        lines += ["### Metric", "", f"➖ Chưa so được metric: {reason}"]
    lines.append("")
    lines.append(f"**Kết luận tuần này (tự đánh giá):** {result['overall']}")
    lines.append("")
    return "\n".join(lines)
