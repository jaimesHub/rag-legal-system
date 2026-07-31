"""Entrypoint for every `make <target>` (docs/plan.md §5, docs/t0.md step 14).

# Phase 3: full Typer app wiring verify-dataset / build-golden / ingest /
# index / search / evaluate / smoke, each a thin wrapper around the
# corresponding src.ingest / src.index / src.retrieve / src.eval function,
# plus `_embedder(settings)` and `_run_context` helpers. This is a minimal
# placeholder so `import src.cli` and `--help` work before that lands.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="rag-legal-system CLI (Phase 1 skeleton — commands land in Phase 3).")


@app.command()
def placeholder() -> None:
    """Placeholder command; replaced by verify-dataset/build-golden/ingest/... in Phase 3."""
    typer.echo("Not implemented yet — see docs/t0.md steps 7-14.")


if __name__ == "__main__":
    app()
