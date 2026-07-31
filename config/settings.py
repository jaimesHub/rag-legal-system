"""Single source of configuration: `.env` -> a validated `Settings` object.

Every other module reads config through this file rather than `os.environ`
directly, so swapping provider / model / dataset revision is always a config
change, never a code change (see CLAUDE.md, docs/plan.md §1).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Only used as the *default* base_dir — never referenced directly by path-
# dependent logic elsewhere. Tests override base_dir explicitly (pitfall #1 in
# docs/t0.md: deriving paths from a module-level constant instead of the
# `base_dir` field makes `tmp_path` isolation silently do nothing).
_REPO_ROOT = Path(__file__).resolve().parents[1]

# Embedding models that accept a `task_type` argument (asymmetric query vs.
# document encoding). Models outside this set ignore the parameter entirely,
# so the Gemini adapter falls back to prepending a task hint to the text.
TASK_TYPE_MODELS = frozenset({"gemini-embedding-001", "text-embedding-004"})

# Models whose output is already L2-normalised at the requested (possibly
# truncated) dimensionality. Everything else needs manual normalisation.
SELF_NORMALISING_MODELS = frozenset({"gemini-embedding-2"})


def _slug(value: str) -> str:
    """Lowercase, non-alphanumeric-collapsed identifier fragment."""
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Provider -------------------------------------------------------
    provider: Literal["gemini", "fake"] = "gemini"
    gemini_api_key: str = ""

    # --- Embedding --------------------------------------------------------
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = Field(default=768, ge=128, le=3072)
    embed_batch_size: int = Field(default=32, ge=1, le=250)

    # --- Generation / judge (unused at T0, declared for T1) --------------
    generator_model: str = "gemini-2.5-flash"
    judge_model: str = "gemini-2.5-pro"

    # --- Qdrant -----------------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = ""  # derived in _derive_collection() when blank

    # --- Dataset (pinned; never "main") ------------------------------------
    dataset_repo_id: str = "GreenNode/zalo-ai-legal-text-retrieval-vn"
    dataset_revision: str = "12d76d4d04b94ceada970fcfbe7fec20bfa97389"

    # --- Chunking (T2/T3 consume this; declared now so it's one source) ----
    chunk_strategy: Literal["article", "khoan"] = "article"
    chunk_max_chars: int = Field(default=2400, ge=200)
    chunk_min_chars: int = Field(default=120, ge=0)

    # Root every derived path hangs off. Overridable so tests point at a tmp
    # dir instead of writing into the real repo (docs/t0.md pitfall #1).
    base_dir: Path = _REPO_ROOT

    @model_validator(mode="after")
    def _derive_collection(self) -> Settings:
        if not self.collection_name:
            # embed_model + embed_dim are baked into the name on purpose:
            # changing either forces a new collection, so two incompatible
            # vector spaces can never land in the same one silently. The
            # fake provider always gets the "fake-embedding" slug instead of
            # whatever embed_model happens to be set to, so a stray
            # PROVIDER=fake run can never overwrite real vectors (docs/t0.md
            # pitfall #2 / failure_log F-006).
            model_slug = "fake-embedding" if self.provider == "fake" else self.embed_model
            object.__setattr__(
                self,
                "collection_name",
                f"legal_{_slug(model_slug)}_{self.embed_dim}",
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supports_task_type(self) -> bool:
        return self.embed_model in TASK_TYPE_MODELS

    @computed_field  # type: ignore[prop-decorator]
    @property
    def needs_manual_normalisation(self) -> bool:
        """True when the returned vectors must be L2-normalised by us."""
        if self.embed_model in SELF_NORMALISING_MODELS:
            return False
        return self.embed_dim != 3072

    # --- Derived paths ------------------------------------------------------
    # All of these hang off `base_dir` — never hard-code Path(__file__) in
    # shared logic, or test isolation via base_dir=tmp_path silently breaks.
    @property
    def raw_dir(self) -> Path:
        return self.base_dir / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.base_dir / "data" / "processed"

    @property
    def golden_dir(self) -> Path:
        return self.base_dir / "data" / "golden"

    @property
    def reports_dir(self) -> Path:
        return self.base_dir / "reports"

    @property
    def artifacts_dir(self) -> Path:
        return self.base_dir / "artifacts"

    def require_api_key(self) -> str:
        if self.provider == "gemini" and not self.gemini_api_key.strip():
            raise RuntimeError(
                "GEMINI_API_KEY is empty. Set it in .env, or run with PROVIDER=fake "
                "for an offline deterministic run."
            )
        return self.gemini_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
