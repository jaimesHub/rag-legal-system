"""Provider contracts (docs/plan.md §1).

Every model call in this project — embedding, generation, judging — goes
through one of these two protocols, so swapping a provider is a config
change (see config.settings + src.providers.registry), not a code change.

Embeddings are the one thing that can't be swapped as freely as generation:
a different model or dimension means a full re-index, which is why
config.settings bakes both into the Qdrant collection name.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

# Asymmetric retrieval: some embedding models encode a query differently from
# a document, which measurably helps retrieval quality.
TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", "SEMANTIC_SIMILARITY"]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into fixed-length vectors."""

    @property
    def model(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str], task_type: TaskType) -> list[list[float]]:
        """Return one vector of length ``dim`` per input, in input order.

        Callers rely on positional alignment between ``texts`` and the
        returned vectors — implementations must never reorder or collapse.
        """
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """Text generation and rubric-based evaluation."""

    @property
    def model(self) -> str: ...

    def complete(self, prompt: str, *, system: str | None = None) -> str: ...

    def judge(self, rubric: str, sample: str) -> dict[str, object]:
        """Score ``sample`` against ``rubric``. Returns at least {"score", "reason"}."""
        ...
