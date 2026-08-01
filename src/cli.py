"""Entrypoint for every `make <target>` (docs/plan.md §5, docs/t0.md step 14).

T0 scope only: verify-dataset / build-golden / ingest / index / search /
evaluate / smoke, plus the optional `fetch` pre-download. Commands that need
BM25 or a dashboard (tokens/sweep/compare/view-eval) are T2 — deliberately not
here yet, see docs/t0.md step 14. Exception: `compare-sample` (cross-project
weekly scorecard vs the sample repo) is added ahead of T2 — see
docs/comparison-framework.md.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from config.settings import Settings, get_settings
from src.eval import compare_sample as cs
from src.eval.golden import build_golden, load_golden
from src.eval.harness import EvalReport, evaluate_retriever, save_report
from src.index.qdrant_store import QdrantStore
from src.ingest import loader as loader_mod
from src.ingest.pipeline import build_passages, load_passages, plan_gold_coverage, write_passages
from src.providers.registry import get_embedding_provider
from src.retrieve.vector import VectorRetriever

app = typer.Typer(no_args_is_help=True, help="rag-legal-system CLI (T0).")
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
    stream=sys.stderr,
)


def _limit_or_none(limit: int) -> int | None:
    """``--limit 0`` means the full corpus."""
    return None if limit <= 0 else limit


def _embedder(settings: Settings):
    """Resolve the embedding provider, failing with a message, not a traceback.

    `get_embedding_provider` -> `GeminiEmbeddingProvider.__init__` ->
    `settings.require_api_key()` raises a plain `RuntimeError` when
    provider=gemini and GEMINI_API_KEY is empty; this turns that into a clean
    exit instead of a stack trace.
    """
    try:
        return get_embedding_provider(settings)
    except RuntimeError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(code=1) from error


def _run_context(settings: Settings, retriever, passages: list) -> dict:
    """Everything needed to reproduce a run, stored inside its report (provenance)."""
    return {
        "dataset_repo_id": settings.dataset_repo_id,
        "dataset_revision": settings.dataset_revision,
        "chunk_strategy": settings.chunk_strategy,
        "n_passages": len(passages),
        "n_documents": len({p.doc_id for p in passages}),
        "retriever": retriever.name,
        "provider": settings.provider,
        "embed_model": settings.embed_model,
        "embed_dim": settings.embed_dim,
        "collection": settings.collection_name,
    }


def _print_report(report: EvalReport, ks: list[int]) -> None:
    table = Table("metric", "value")
    for name in sorted(report.metrics):
        if name == "n_queries":
            continue
        table.add_row(name, f"{report.metrics[name]:.4f}")
    console.print(table)
    console.print(
        f"latency ms: mean={report.latency_ms['mean']} "
        f"p50={report.latency_ms['p50']} p95={report.latency_ms['p95']}"
    )
    console.print(f"queries={report.n_queries}  retriever={report.retriever}")

    if report.failures:
        console.print(f"\n[bold]Total misses at k={max(ks)}[/] (first {len(report.failures)}):")
        for failure in report.failures[:5]:
            console.print(f"  • {failure.query[:80]}")
            console.print(f"    expected={failure.expected} got={failure.retrieved[:3]}")


@app.command()
def fetch() -> None:
    """Pre-download the pinned dataset into data/raw/.

    Optional: any command that needs data downloads it on demand. This is for
    warming a slow connection up front, or checking what's already cached.
    """
    settings = get_settings()
    console.print(
        f"[bold]{settings.dataset_repo_id}[/] @ {settings.dataset_revision[:8]} "
        f"-> {settings.raw_dir}"
    )

    total = 0
    table = Table("file", "size", "state")
    for filename in loader_mod.ALL_FILES:
        # Checked before the call, since the call is what creates the file.
        cached = (settings.raw_dir / filename).exists()
        path = loader_mod.download_file(settings, filename)
        size = path.stat().st_size
        total += size
        table.add_row(filename, f"{size / 1_048_576:.1f} MB", "cached" if cached else "downloaded")
    console.print(table)
    console.print(f"Total {total / 1_048_576:.1f} MB in {settings.raw_dir}")


@app.command("verify-dataset")
def verify_dataset() -> None:
    """Download the pinned dataset and assert its schema and counts (docs/t0.md step 7)."""
    settings = get_settings()
    console.print(f"[bold]{settings.dataset_repo_id}[/] @ {settings.dataset_revision[:8]}")

    result = loader_mod.verify_dataset(settings)

    table = Table("check", "expected", "observed", "ok")
    for check in result["checks"]:
        table.add_row(
            check["check"],
            str(check["expected"]),
            str(check["observed"]),
            "[green]yes[/]" if check["ok"] else "[red]NO[/]",
        )
    console.print(table)
    console.print(
        f"Duplicate query rows in queries.jsonl: [yellow]{result['duplicate_query_rows']}[/] "
        "(deduplicated)"
    )
    console.print(
        f"Query ids in both train and test qrels: [yellow]{result['overlap_count']}[/] "
        "(excluded from dev)"
    )

    if not result["all_ok"]:
        console.print("[red]Some checks failed — the pin may have moved.[/]")
        raise typer.Exit(code=1)
    console.print("[green]Dataset schema and counts verified.[/]")


@app.command("build-golden")
def build_golden_cmd() -> None:
    """Build data/golden/dev.jsonl and the frozen test.jsonl (docs/t0.md step 9)."""
    settings = get_settings()
    stats = build_golden(settings)

    table = Table("split", "queries", "labels", "labels/query", "multi-label", "excluded")
    for name, stat in stats.items():
        table.add_row(
            name,
            str(stat.n_queries),
            str(stat.n_labels),
            f"{stat.mean_labels_per_query:.3f}",
            str(stat.multi_label_queries),
            str(stat.excluded_overlap),
        )
    console.print(table)
    console.print(f"Written to {settings.golden_dir}")


@app.command()
def ingest(
    limit: int = typer.Option(500, help="Documents to ingest; 0 = full corpus (T2+)."),
    gold_fraction: float = typer.Option(
        0.5, help="Share of the budget reserved for gold documents."
    ),
) -> None:
    """Clean, chunk, and write processed passages (docs/t0.md step 10)."""
    settings = get_settings()
    doc_limit = _limit_or_none(limit)

    gold_ids: set[str] = set()
    if doc_limit is not None:
        try:
            golden = load_golden(settings, "test")
        except FileNotFoundError:
            console.print("[yellow]No golden set yet — building it first.[/]")
            build_golden(settings)
            golden = load_golden(settings, "test")
        gold_ids, covered_examples = plan_gold_coverage(golden, doc_limit, gold_fraction)
        console.print(
            f"Slice is gold-covering: forcing {len(gold_ids)} gold documents "
            f"for {len(covered_examples)} test queries, filling the rest with distractors."
        )

    started = time.perf_counter()
    passages, audit = build_passages(settings, limit=doc_limit, gold_doc_ids=gold_ids)
    path = write_passages(settings, passages, audit)
    elapsed = time.perf_counter() - started

    table = Table("metric", "value")
    table.add_row("documents", str(audit.documents))
    table.add_row("passages", str(audit.passages))
    table.add_row("chunk strategy", settings.chunk_strategy)
    table.add_row(
        "chars mean / p90 / max", f"{audit.chars_mean} / {audit.chars_p90} / {audit.chars_max}"
    )
    table.add_row("metadata parse failures", str(audit.metadata_parse_failures))
    table.add_row("gold docs found", f"{audit.gold_documents_found}/{len(gold_ids)}")
    table.add_row("year range", f"{audit.year_min}–{audit.year_max}")
    table.add_row("elapsed", f"{elapsed:.1f}s")
    console.print(table)

    top_types = list(audit.doc_type_counts.items())[:6]
    console.print("Document types: " + ", ".join(f"{k}={v}" for k, v in top_types))
    console.print(f"Written to {path}")


@app.command()
def index(
    limit: int = typer.Option(0, help="Cap passages to embed; 0 = all processed passages."),
    recreate: bool = typer.Option(False, help="Drop and recreate the collection first."),
) -> None:
    """Embed processed passages and upsert them into Qdrant (docs/t0.md step 11)."""
    settings = get_settings()
    passages = load_passages(settings)
    if limit > 0:
        passages = passages[:limit]

    embedder = _embedder(settings)
    store = QdrantStore(settings)
    store.ensure_collection(recreate=recreate)

    console.print(
        f"Embedding {len(passages)} passages with [bold]{embedder.model}[/] "
        f"(dim={embedder.dim}) into [bold]{store.collection}[/]"
    )

    started = time.perf_counter()
    batch_size = settings.embed_batch_size
    upserted = 0
    for start in range(0, len(passages), batch_size):
        batch = passages[start : start + batch_size]
        vectors = embedder.embed([p.embed_text for p in batch], task_type="RETRIEVAL_DOCUMENT")
        upserted += store.upsert(batch, vectors)
        console.print(f"  upserted {upserted}/{len(passages)}", end="\r")
    elapsed = time.perf_counter() - started

    console.print(f"\nUpserted {upserted} passages in {elapsed:.1f}s")
    console.print(store.collection_info())


@app.command()
def search(
    query: str = typer.Option(..., "--query", "-q", help="Query text."),
    k: int = typer.Option(10, help="Results to return."),
) -> None:
    """Ad-hoc vector search against the current collection (docs/t0.md step 12)."""
    settings = get_settings()
    retriever = VectorRetriever(QdrantStore(settings), _embedder(settings))

    started = time.perf_counter()
    hits = retriever.retrieve(query, k)
    elapsed = (time.perf_counter() - started) * 1000

    table = Table("#", "score", "doc_id", "title")
    for rank, hit in enumerate(hits, start=1):
        table.add_row(str(rank), f"{hit.score:.4f}", hit.doc_id, (hit.title or "")[:70])
    console.print(table)
    console.print(f"{len(hits)} hits in {elapsed:.0f} ms via {retriever.name}")


@app.command()
def evaluate(
    split: str = typer.Option(
        "test", help="'test' is the benchmark split; 'dev' is not evaluated."
    ),
    retriever: str = typer.Option("vector", help="Retriever to evaluate. Only 'vector' at T0."),
    k: int = typer.Option(10, help="Top-k cutoff."),
    limit: int = typer.Option(0, help="Cap queries evaluated; 0 = all."),
    label: str = typer.Option("", help="Human-readable run name, used when comparing later."),
) -> None:
    """Run the harness and print a metric report (docs/t0.md step 13)."""
    settings = get_settings()
    if retriever != "vector":
        console.print(f"[red]Unknown retriever {retriever!r}. Only 'vector' exists at T0.[/]")
        raise typer.Exit(code=1)

    examples = load_golden(settings, split)
    passages = load_passages(settings)
    engine = VectorRetriever(QdrantStore(settings), _embedder(settings))

    # On a partial ingest slice (e.g. `--limit 500`), a query whose gold
    # document was never indexed can only score 0 — that's not a retrieval
    # failure, it's an out-of-scope query. Excluding it keeps the number
    # interpretable; the count dropped is printed so nothing vanishes silently.
    indexed_docs = {p.doc_id for p in passages}
    before = len(examples)
    examples = [e for e in examples if set(e.relevant_doc_ids) <= indexed_docs]
    if before != len(examples):
        console.print(
            f"[yellow]Evaluating {len(examples)}/{before} queries[/] — the rest have "
            "gold documents outside the current ingest slice."
        )
    if limit > 0:
        examples = examples[:limit]
    if not examples:
        console.print("[red]No evaluable queries. Ingest a corpus covering the gold set.[/]")
        raise typer.Exit(code=1)

    ks = sorted({1, 5, k})
    report = evaluate_retriever(
        engine,
        examples,
        ks=ks,
        split=split,
        label=label,
        context=_run_context(settings, engine, passages),
    )

    _print_report(report, ks)
    path = save_report(report, settings.artifacts_dir / "eval")
    console.print(f"\nReport: {path}")


@app.command()
def smoke(
    limit: int = typer.Option(500, help="Documents in the smoke slice; 0 = full corpus."),
    k: int = typer.Option(10, help="Top-k cutoff."),
) -> None:
    """T0 deliverable: verify -> golden -> ingest -> index -> evaluate, one command.

    PROVIDER=fake makes this fully offline (no GEMINI_API_KEY, no network beyond
    the dataset download). The numbers it prints are a regression tripwire, not
    a baseline quality claim — see CLAUDE.md and docs/t0.md step 17.
    """
    console.rule("1/5 verify dataset")
    verify_dataset()
    console.rule("2/5 build golden splits")
    build_golden_cmd()
    console.rule("3/5 ingest")
    ingest(limit=limit, gold_fraction=0.5)
    console.rule("4/5 index")
    index(limit=0, recreate=True)
    console.rule("5/5 evaluate")
    evaluate(split="test", retriever="vector", k=k, limit=0, label="t0-smoke")
    console.rule("[green]smoke complete[/]")


def _print_compare_sample(result: dict) -> None:
    week = result["week"]
    console.rule(f"[bold]So với dự án mẫu — T{week}[/] (overall: {result['overall']})")

    axes_table = Table("Trục", "Trạng thái", "Bằng chứng", title="Scorecard 7 trục")
    for name, axis in result["axes"].items():
        axes_table.add_row(name, axis["status"], axis["evidence"])
    console.print(axes_table)

    metric = result["metric"]
    if metric.get("comparable"):
        mt = Table("metric", "current", f"sample ({metric['sample_label']})", "Δ")
        for m in sorted(metric["current"]):
            delta = metric["delta"][m]
            color = "green" if delta >= 0 else "red"
            mt.add_row(
                m,
                f"{metric['current'][m]:.4f}",
                f"{metric['sample'][m]:.4f}",
                f"[{color}]{delta:+.4f}[/]",
            )
        console.print(mt)
        bonus = "≥ mẫu (bonus)" if metric.get("beats_sample") else "chưa vượt mẫu (không phải cửa)"
        console.print(f"Bar (quyết định 3): có số thật + giải thích = ĐẠT. {bonus}.")
    else:
        console.print(f"[yellow]➖ Metric chưa so được:[/] {(metric.get('reasons') or ['?'])[0]}")

    cur = result["structural"]["current"]
    smp = result["structural"]["sample"]
    console.print(
        f"\n[dim]struct: current src={cur['src_files']} cli={cur['cli_commands']} "
        f"targets={cur['make_targets']} tests={cur['test_functions']} F={cur['failure_entries']} | "
        f"sample src={smp['src_files']} cli={smp['cli_commands']} targets={smp['make_targets']} "
        f"tests={smp['test_functions']} F={smp['failure_entries']}[/]"
    )


@app.command(name="compare-sample")
def compare_sample_cmd(
    week: int = typer.Option(..., "--week", "-w", help="Tuần cần so (0..8)."),
    retriever: str = typer.Option("", help="Retriever anchor; rỗng = mặc định theo tuần."),
    report: Path | None = typer.Option(None, help="Report cụ thể; mặc định = run test mới nhất."),
    sample_baselines: Path = typer.Option(
        Path("docs/sample-baselines.yaml"), help="File số chuẩn của mẫu."
    ),
    current_root: Path | None = typer.Option(None, help="Gốc dự án hiện tại (mặc định base_dir)."),
    sample_root: Path = typer.Option(Path("../aie-rag-sample-project"), help="Gốc dự án mẫu."),
    emit_md: bool = typer.Option(False, "--emit-md", help="In block markdown để dán vào report."),
    json_out: Path | None = typer.Option(None, "--json", help="Ghi kết quả JSON ra path."),
    validate_sample: bool = typer.Option(
        False, "--validate-sample", help="Cảnh báo nếu HEAD của mẫu khác sample_commit trong YAML."
    ),
) -> None:
    """Scorecard 7 trục + guard metric cùng-cấu-hình vs dự án mẫu (docs/comparison-framework.md).

    Luôn exit 0 — đây là bảng điểm tham chiếu, KHÔNG phải cổng build.
    """
    settings = get_settings()
    root = current_root or settings.base_dir
    baselines_path = sample_baselines if sample_baselines.is_absolute() else root / sample_baselines

    result = cs.compare_sample(
        week=week,
        current_root=root,
        sample_root=sample_root,
        baselines_path=baselines_path,
        eval_dir=settings.artifacts_dir / "eval",
        retriever=retriever or None,
        report_path=report,
    )

    if validate_sample:
        head = _sample_head(sample_root)
        pinned = result.get("sample_commit")
        if head and pinned and head != pinned:
            console.print(
                f"[yellow]⚠ sample HEAD {head[:10]} ≠ sample_commit {str(pinned)[:10]} (YAML)[/] "
                "— chép lại số mẫu rồi cập nhật meta.sample_commit."
            )
        elif head and pinned:
            console.print("[green]✓ sample_commit khớp HEAD của mẫu.[/]")

    _print_compare_sample(result)

    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"\nJSON: {json_out}")
    else:
        default_json = settings.artifacts_dir / "compare_sample" / f"compare_sample_week{week}.json"
        default_json.parent.mkdir(parents=True, exist_ok=True)
        default_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"\nJSON: {default_json}")

    if emit_md:
        console.rule("markdown")
        console.print(cs.to_markdown(result))


def _sample_head(sample_root: Path) -> str | None:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(sample_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


if __name__ == "__main__":
    app()
