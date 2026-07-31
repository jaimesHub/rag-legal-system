"""Deterministic, offline providers.

These exist so the full pipeline (ingest -> index -> retrieve -> evaluate)
can run with no network access, no API key, and no cost — for the T0 smoke
test and for the test suite. The embeddings are a hashed bag-of-words
projection: not semantically meaningful, but stable across runs and weakly
correlated with lexical overlap, which is enough to prove the wiring is
correct end to end.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from src.providers.base import TaskType

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


class FakeEmbeddingProvider:
    """Hash-based vectoriser: deterministic, dimension-correct, L2-normalised."""

    def __init__(self, dim: int = 768, model: str = "fake-embedding") -> None:
        self._dim = dim
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str], task_type: TaskType) -> list[list[float]]:
        del task_type  # the fake embedder is intentionally symmetric
        vectors = np.zeros((len(texts), self._dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in _tokenize(text):
                # blake2b is stable across Python versions/platforms, unlike
                # the builtin hash() (which is salted per-process) — that
                # salting is exactly what would break determinism here.
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                bucket = int.from_bytes(digest[:4], "big") % self._dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vectors[row, bucket] += sign
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)  # avoid NaN for empty/all-punct text
        return (vectors / norms).tolist()


class FakeLLMProvider:
    """Echoing completion + a deterministic pseudo-judge."""

    def __init__(self, model: str = "fake-llm") -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        del system
        return f"[fake:{self._model}] {prompt[:200]}"

    def judge(self, rubric: str, sample: str) -> dict[str, object]:
        del rubric  # the fake judge ignores the rubric — it only needs to be stable
        digest = hashlib.blake2b(sample.encode("utf-8"), digest_size=2).digest()
        score = round((int.from_bytes(digest, "big") % 101) / 100, 2)
        return {"score": score, "reason": "deterministic fake judge", "parsed": True}
