from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import Settings


def _s(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_collection_name_encodes_model_and_dimension():
    """Changing either forces a re-index, so both must be in the name."""
    settings = _s(embed_model="gemini-embedding-001", embed_dim=768)
    assert settings.collection_name == "legal_gemini_embedding_001_768"


def test_different_dimension_yields_a_different_collection():
    a = _s(embed_model="gemini-embedding-001", embed_dim=768).collection_name
    b = _s(embed_model="gemini-embedding-001", embed_dim=1536).collection_name
    assert a != b


def test_different_model_yields_a_different_collection():
    a = _s(embed_model="gemini-embedding-001", embed_dim=768).collection_name
    b = _s(embed_model="gemini-embedding-2", embed_dim=768).collection_name
    assert a != b


def test_explicit_collection_name_is_respected():
    assert _s(collection_name="my_collection").collection_name == "my_collection"


def test_fake_provider_gets_its_own_collection():
    """Offline vectors must never land in the real collection (F-006)."""
    fake = _s(provider="fake", embed_model="gemini-embedding-001", embed_dim=768)
    real = _s(provider="gemini", embed_model="gemini-embedding-001", embed_dim=768)
    assert fake.collection_name == "legal_fake_embedding_768"
    assert fake.collection_name != real.collection_name


def test_fake_provider_ignores_whatever_embed_model_is_set_to():
    """A stray PROVIDER=fake run must not overwrite real vectors even if
    EMBED_MODEL was left pointing at the real model (docs/t0.md pitfall #2)."""
    a = _s(provider="fake", embed_model="gemini-embedding-001", embed_dim=768).collection_name
    b = _s(provider="fake", embed_model="gemini-embedding-2", embed_dim=768).collection_name
    assert a == b == "legal_fake_embedding_768"


def test_task_type_support_is_model_dependent():
    assert _s(embed_model="gemini-embedding-001").supports_task_type is True
    # gemini-embedding-2 has no task_type parameter.
    assert _s(embed_model="gemini-embedding-2").supports_task_type is False


def test_truncated_gemini_001_vectors_need_manual_normalisation():
    assert _s(embed_model="gemini-embedding-001", embed_dim=768).needs_manual_normalisation is True
    assert (
        _s(embed_model="gemini-embedding-001", embed_dim=3072).needs_manual_normalisation is False
    )


def test_gemini_embedding_2_self_normalises():
    assert _s(embed_model="gemini-embedding-2", embed_dim=768).needs_manual_normalisation is False


def test_fake_provider_needs_no_api_key():
    assert _s(provider="fake", gemini_api_key="").require_api_key() == ""


def test_gemini_provider_without_a_key_raises_a_clear_error():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        _s(provider="gemini", gemini_api_key="").require_api_key()


def test_dataset_pin_is_a_commit_not_a_branch():
    revision = _s().dataset_revision
    assert len(revision) == 40 and revision != "main"


def test_base_dir_derives_every_processed_path():
    """The isolation mechanism itself: paths must hang off base_dir, not
    Path(__file__) (docs/t0.md pitfall #1)."""
    settings = _s(base_dir=Path("/tmp/some-tmp-dir"))
    assert settings.raw_dir == Path("/tmp/some-tmp-dir/data/raw")
    assert settings.processed_dir == Path("/tmp/some-tmp-dir/data/processed")
    assert settings.golden_dir == Path("/tmp/some-tmp-dir/data/golden")
    assert settings.artifacts_dir == Path("/tmp/some-tmp-dir/artifacts")
