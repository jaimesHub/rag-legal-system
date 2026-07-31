from __future__ import annotations

from src.ingest.metadata import build_metadata, parse_corpus_id


def test_parses_thong_tu_id():
    meta = parse_corpus_id("01/2009/tt-bnn+1")
    assert meta.doc_key == "01/2009/tt-bnn"
    assert meta.doc_number == "01"
    assert meta.year == 2009
    assert meta.doc_type == "thong_tu"
    assert meta.issuer == "bnn"
    assert meta.article_index == 1
    assert meta.parse_ok


def test_national_assembly_code_is_not_an_issuer():
    """59/2020/qh14 — the "14" is the assembly term, not an issuing body."""
    meta = parse_corpus_id("59/2020/qh14+189")
    assert meta.doc_type == "luat"
    assert meta.issuer == "qh"
    assert meta.article_index == 189
    assert meta.parse_ok


def test_nghi_dinh_with_vietnamese_diacritic_code():
    meta = parse_corpus_id("100/2019/nđ-cp+6")
    assert meta.doc_type == "nghi_dinh"
    assert meta.issuer == "cp"
    assert meta.year == 2019


def test_malformed_id_is_flagged_not_raised():
    meta = parse_corpus_id("not-a-legal-id")
    assert meta.parse_ok is False
    assert meta.doc_key == "not-a-legal-id"


def test_implausible_year_is_rejected():
    meta = parse_corpus_id("01/1899/tt-bnn+1")
    assert meta.year is None
    assert meta.parse_ok is False


def test_unknown_doc_type_is_flagged():
    meta = parse_corpus_id("01/2009/zz-xyz+1")
    assert meta.parse_ok is False
    assert meta.issuer == "xyz"


def test_missing_article_separator_is_flagged():
    meta = parse_corpus_id("01/2009/tt-bnn")
    assert meta.parse_ok is False
    assert meta.doc_key == "01/2009/tt-bnn"


def test_title_supplies_article_number_and_heading():
    meta = build_metadata("01/2009/tt-bnn+1", "Điều 1. Phạm vi áp dụng")
    assert meta.article_no == "1"
    assert meta.article_heading == "Phạm vi áp dụng"


def test_title_without_dieu_prefix_still_kept_as_heading():
    meta = build_metadata("01/2009/tt-bnn+1", "Phụ lục kèm theo")
    assert meta.article_no is None
    assert meta.article_heading == "Phụ lục kèm theo"
