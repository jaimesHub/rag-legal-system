from __future__ import annotations

import json

import pytest

from src.eval import golden as golden_mod
from src.ingest.loader import QrelSet
from src.schemas import Query


@pytest.fixture
def fake_dataset(monkeypatch):
    """Three train queries and two test queries, with q3 overlapping both."""
    queries = {f"q{i}": Query(query_id=f"q{i}", text=f"câu hỏi {i}") for i in range(1, 6)}
    train = QrelSet(
        name="train",
        labels={
            "q1": {"d1": 1},
            "q2": {"d2": 1, "d3": 1},
            "q3": {"d4": 1},  # also in test -> must be dropped from dev
        },
    )
    test = QrelSet(name="test", labels={"q3": {"d4": 1}, "q4": {"d5": 1}})

    monkeypatch.setattr(golden_mod, "load_queries", lambda s: (queries, 7))
    monkeypatch.setattr(
        golden_mod, "load_qrels", lambda s, split: train if split == "train" else test
    )


def test_overlapping_queries_are_excluded_from_dev(settings, fake_dataset):
    stats = golden_mod.build_golden(settings)
    assert stats["dev"].n_queries == 2
    assert stats["dev"].excluded_overlap == 1
    dev_ids = {e.query_id for e in golden_mod.load_golden(settings, "dev")}
    assert "q3" not in dev_ids


def test_overlapping_queries_stay_in_the_test_split(settings, fake_dataset):
    golden_mod.build_golden(settings)
    test_ids = {e.query_id for e in golden_mod.load_golden(settings, "test")}
    assert test_ids == {"q3", "q4"}


def test_multi_label_queries_are_counted(settings, fake_dataset):
    stats = golden_mod.build_golden(settings)
    assert stats["dev"].multi_label_queries == 1
    assert stats["dev"].n_labels == 3


def test_manifest_records_provenance_and_exclusions(settings, fake_dataset):
    golden_mod.build_golden(settings)
    manifest = json.loads(
        (settings.golden_dir / golden_mod.MANIFEST_FILE).read_text(encoding="utf-8")
    )
    assert manifest["dataset_revision"] == settings.dataset_revision
    assert manifest["duplicate_query_rows_dropped"] == 7
    assert manifest["overlap_query_ids_excluded_from_dev"] == ["q3"]


def test_labelled_query_without_text_is_skipped(settings, monkeypatch):
    monkeypatch.setattr(golden_mod, "load_queries", lambda s: ({}, 0))
    monkeypatch.setattr(
        golden_mod,
        "load_qrels",
        lambda s, split: QrelSet(name=split, labels={"ghost": {"d1": 1}}),
    )
    stats = golden_mod.build_golden(settings)
    assert stats["dev"].n_queries == 0


def test_unknown_split_is_rejected(settings, fake_dataset):
    golden_mod.build_golden(settings)
    with pytest.raises(ValueError, match="must be 'dev' or 'test'"):
        golden_mod.load_golden(settings, "train")


def test_missing_golden_file_raises_actionable_error(settings):
    with pytest.raises(FileNotFoundError, match="make golden"):
        golden_mod.load_golden(settings, "dev")
