"""Provider selection — the single place that maps config to implementations.

Nothing outside this module should import `src.providers.fake` or
`src.providers.gemini` directly; going through here is what makes
"change PROVIDER in .env" the entire story for switching backends.
"""

from __future__ import annotations

from config.settings import Settings, get_settings
from src.providers.base import EmbeddingProvider, LLMProvider

_ROLES = ("generator", "judge")


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    if settings.provider == "fake":
        from src.providers.fake import FakeEmbeddingProvider

        return FakeEmbeddingProvider(dim=settings.embed_dim)

    from src.providers.gemini import GeminiEmbeddingProvider

    return GeminiEmbeddingProvider(settings)


def get_llm_provider(settings: Settings | None = None, *, role: str = "generator") -> LLMProvider:
    """``role`` is "generator" or "judge".

    The judge defaults to a different model than the generator
    (config.settings.judge_model vs. generator_model) to reduce
    self-preference bias — relevant from T1 onward, not used yet at T0.
    """
    settings = settings or get_settings()
    if role not in _ROLES:
        raise ValueError(f"Unknown role: {role!r} (expected one of {_ROLES})")

    if settings.provider == "fake":
        from src.providers.fake import FakeLLMProvider

        return FakeLLMProvider(model=f"fake-{role}")

    from src.providers.gemini import GeminiLLMProvider

    model = settings.judge_model if role == "judge" else settings.generator_model
    return GeminiLLMProvider(settings, model=model)
