"""Gemini adapters for the embedding and LLM contracts.

Two model-family quirks are absorbed here so the rest of the codebase never
has to know about them:

1. ``task_type`` is only honoured by some embedding models (see
   config.settings.TASK_TYPE_MODELS). For models without support we prepend
   a short natural-language task hint to the text instead.
2. Passing a bare list of strings to ``embed_content`` can make some models
   return a single aggregated embedding for the whole batch instead of one
   per string. Wrapping every input in its own ``types.Content`` is what
   forces per-input embeddings — we do that unconditionally and then assert
   the returned count matches, so a future regression fails loudly instead
   of silently degrading retrieval quality.
"""

from __future__ import annotations

import json
import logging

import numpy as np
from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config.settings import Settings
from src.providers.base import TaskType

logger = logging.getLogger(__name__)

# Retry only transport/quota errors — a malformed request (bad model name,
# bad argument) should fail immediately, not after five slow retries.
_RETRYABLE = (genai.errors.ServerError, genai.errors.ClientError)

_TASK_HINTS: dict[str, str] = {
    "RETRIEVAL_DOCUMENT": "Văn bản pháp luật cần được lập chỉ mục để tra cứu:",
    "RETRIEVAL_QUERY": "Câu hỏi tra cứu pháp luật:",
    "SEMANTIC_SIMILARITY": "Đoạn văn bản:",
}

_RETRY_KWARGS = dict(
    retry=retry_if_exception_type(_RETRYABLE),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # guard against a zero vector -> NaN
    return vectors / norms


class GeminiEmbeddingProvider:
    """EmbeddingProvider backed by the Gemini embeddings API."""

    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self._settings = settings
        self._client = client or genai.Client(api_key=settings.require_api_key())

    @property
    def model(self) -> str:
        return self._settings.embed_model

    @property
    def dim(self) -> int:
        return self._settings.embed_dim

    def embed(self, texts: list[str], task_type: TaskType) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        batch_size = self._settings.embed_batch_size
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            out.extend(self._embed_batch(batch, task_type))
        return out

    @retry(**_RETRY_KWARGS)
    def _embed_batch(self, batch: list[str], task_type: TaskType) -> list[list[float]]:
        settings = self._settings
        payload = batch

        config_kwargs: dict[str, object] = {"output_dimensionality": settings.embed_dim}
        if settings.supports_task_type:
            config_kwargs["task_type"] = task_type
        else:
            hint = _TASK_HINTS.get(task_type, "")
            payload = [f"{hint}\n{text}" if hint else text for text in batch]

        response = self._client.models.embed_content(
            model=settings.embed_model,
            # One Content per input, never a bare list of strings — see the
            # module docstring for why this matters.
            contents=[types.Content(parts=[types.Part.from_text(text=t)]) for t in payload],
            config=types.EmbedContentConfig(**config_kwargs),
        )

        embeddings = response.embeddings or []
        if len(embeddings) != len(batch):
            raise RuntimeError(
                f"{settings.embed_model} returned {len(embeddings)} embeddings for "
                f"{len(batch)} inputs — the API aggregated the batch instead of "
                "embedding each input separately."
            )

        vectors = np.asarray([e.values for e in embeddings], dtype=np.float32)
        if vectors.shape[1] != settings.embed_dim:
            raise RuntimeError(f"Expected dimension {settings.embed_dim}, got {vectors.shape[1]}.")
        if settings.needs_manual_normalisation:
            vectors = _l2_normalize(vectors)
        return vectors.tolist()


class GeminiLLMProvider:
    """LLMProvider backed by Gemini's generate_content."""

    def __init__(
        self,
        settings: Settings,
        *,
        model: str | None = None,
        client: genai.Client | None = None,
    ) -> None:
        self._settings = settings
        self._model = model or settings.generator_model
        self._client = client or genai.Client(api_key=settings.require_api_key())

    @property
    def model(self) -> str:
        return self._model

    @retry(**_RETRY_KWARGS)
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        config = types.GenerateContentConfig(system_instruction=system) if system else None
        response = self._client.models.generate_content(
            model=self._model, contents=prompt, config=config
        )
        return response.text or ""

    def judge(self, rubric: str, sample: str) -> dict[str, object]:
        prompt = (
            f"{rubric}\n\n---\nSAMPLE:\n{sample}\n---\n"
            'Reply with JSON only: {"score": <number>, "reason": "<short reason>"}'
        )
        raw = self.complete(prompt)
        try:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Judge returned non-JSON output; recording as unparsed.")
            return {"score": None, "reason": raw[:500], "parsed": False}
        return {**parsed, "parsed": True}
