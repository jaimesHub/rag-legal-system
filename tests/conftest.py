from __future__ import annotations

import pytest

from config.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Offline settings with every derived path inside a temp dir.

    base_dir is what isolates a test run — without it the suite writes golden and
    processed files into the real repo (docs/t0.md pitfall #1).
    """
    return Settings(
        base_dir=tmp_path,
        provider="fake",
        gemini_api_key="",
        embed_model="fake-embedding",
        # 128 is the smallest dimension Gemini's MRL truncation supports, and the
        # smallest Settings will accept.
        embed_dim=128,
        embed_batch_size=8,
        _env_file=None,
    )
