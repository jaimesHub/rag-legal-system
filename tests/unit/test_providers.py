from __future__ import annotations

import numpy as np
import pytest

from config.settings import Settings
from src.providers.base import EmbeddingProvider, LLMProvider
from src.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from src.providers.registry import get_embedding_provider, get_llm_provider


def test_fake_provider_satisfies_the_contract():
    provider = FakeEmbeddingProvider(dim=32)
    assert isinstance(provider, EmbeddingProvider)
    assert isinstance(FakeLLMProvider(), LLMProvider)


def test_embed_returns_one_vector_per_text_in_order():
    provider = FakeEmbeddingProvider(dim=32)
    vectors = provider.embed(["một", "hai", "ba"], task_type="RETRIEVAL_DOCUMENT")
    assert len(vectors) == 3
    assert all(len(v) == 32 for v in vectors)


def test_embed_dim_matches_the_constructor_argument():
    assert FakeEmbeddingProvider(dim=128).dim == 128


def test_embeddings_are_deterministic():
    provider = FakeEmbeddingProvider(dim=32)
    a = provider.embed(["luật đê điều"], task_type="RETRIEVAL_DOCUMENT")
    b = provider.embed(["luật đê điều"], task_type="RETRIEVAL_DOCUMENT")
    assert a == b


def test_embeddings_are_deterministic_across_task_types():
    """The fake embedder is intentionally symmetric — task_type is ignored."""
    provider = FakeEmbeddingProvider(dim=32)
    doc = provider.embed(["luật đê điều"], task_type="RETRIEVAL_DOCUMENT")
    query = provider.embed(["luật đê điều"], task_type="RETRIEVAL_QUERY")
    assert doc == query


def test_embeddings_are_l2_normalised():
    provider = FakeEmbeddingProvider(dim=64)
    vector = np.asarray(provider.embed(["xử phạt vi phạm"], task_type="RETRIEVAL_QUERY")[0])
    assert np.isclose(np.linalg.norm(vector), 1.0)


def test_lexical_overlap_scores_higher_than_unrelated_text():
    """Enough signal for the offline smoke test to be meaningful."""
    provider = FakeEmbeddingProvider(dim=256)
    query, related, unrelated = provider.embed(
        [
            "quay đầu xe trên đường cao tốc",
            "xử phạt hành vi quay đầu xe trên đường cao tốc",
            "quy định về kiểm dịch thực vật nhập khẩu",
        ],
        task_type="RETRIEVAL_QUERY",
    )
    assert np.dot(query, related) > np.dot(query, unrelated)


def test_embed_empty_list_returns_empty():
    assert FakeEmbeddingProvider(dim=8).embed([], task_type="RETRIEVAL_QUERY") == []


def test_text_with_no_tokens_yields_a_finite_vector():
    """A zero vector must not divide by zero into NaN."""
    vector = np.asarray(FakeEmbeddingProvider(dim=8).embed(["!!!"], task_type="RETRIEVAL_QUERY")[0])
    assert np.all(np.isfinite(vector))


def test_fake_llm_complete_is_deterministic_and_echoes_the_prompt():
    llm = FakeLLMProvider()
    assert llm.complete("hello") == llm.complete("hello")
    assert "hello" in llm.complete("hello")


def test_fake_llm_judge_is_deterministic_and_bounded():
    llm = FakeLLMProvider()
    result = llm.judge("rubric", "sample")
    assert result == llm.judge("rubric", "sample")
    assert 0.0 <= result["score"] <= 1.0
    assert result["parsed"] is True


def test_registry_returns_fake_when_provider_is_fake(settings):
    provider = get_embedding_provider(settings)
    assert isinstance(provider, FakeEmbeddingProvider)
    assert provider.model == "fake-embedding"
    assert provider.dim == settings.embed_dim


def test_judge_and_generator_get_distinct_models(settings):
    assert get_llm_provider(settings, role="judge").model != (
        get_llm_provider(settings, role="generator").model
    )


def test_unknown_role_is_rejected(settings):
    with pytest.raises(ValueError, match="Unknown role"):
        get_llm_provider(settings, role="reranker")


def test_gemini_provider_requires_an_api_key():
    settings = Settings(provider="gemini", gemini_api_key="", _env_file=None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        settings.require_api_key()
