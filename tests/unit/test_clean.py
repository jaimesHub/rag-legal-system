from __future__ import annotations

import unicodedata

from src.ingest.clean import clean_text, clean_title


def test_collapses_spaces_but_preserves_newlines():
    """The chunker finds Khoản boundaries by newline, so newlines must survive."""
    cleaned = clean_text("1.  Khoản một\n2.   Khoản hai")
    assert cleaned == "1. Khoản một\n2. Khoản hai"


def test_normalises_to_nfc():
    decomposed = unicodedata.normalize("NFD", "Điều")
    assert decomposed != "Điều"
    assert clean_text(decomposed) == "Điều"


def test_nfc_makes_visually_identical_words_compare_equal():
    a = clean_text(unicodedata.normalize("NFD", "quyết định"))
    b = clean_text(unicodedata.normalize("NFC", "quyết định"))
    assert a == b


def test_collapses_excess_blank_lines():
    assert clean_text("a\n\n\n\n\nb") == "a\n\nb"


def test_strips_trailing_whitespace_before_newline():
    assert clean_text("a   \nb") == "a\nb"


def test_handles_empty_input():
    assert clean_text("") == ""
    assert clean_title("") == ""


def test_clean_title_flattens_whitespace():
    assert clean_title("  Điều 1.   Phạm vi  ") == "Điều 1. Phạm vi"
