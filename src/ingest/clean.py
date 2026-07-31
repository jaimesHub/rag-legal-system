"""Text normalisation for corpus title/text before chunking.

Deliberately conservative: newlines are preserved because the chunker relies on
them to find Khoản boundaries, and Vietnamese diacritics are normalised to NFC
so that the same word always hashes and tokenises identically (without this,
visually identical words can tokenise differently and lexical search silently
misses matches from T2 onward).
"""

from __future__ import annotations

import re
import unicodedata

# Collapse runs of spaces/tabs (incl. the U+200B zero-width space some legal
# text ships with) but never collapse newlines — those carry chunk structure.
_INLINE_WS = re.compile(r"[ \t​]+")
_TRAILING_WS = re.compile(r"[ \t]+\n")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    if not text:
        return ""
    out = unicodedata.normalize("NFC", text)
    out = out.replace("\r\n", "\n").replace("\r", "\n")
    out = _INLINE_WS.sub(" ", out)
    out = _TRAILING_WS.sub("\n", out)
    out = _MANY_NEWLINES.sub("\n\n", out)
    return out.strip()


def clean_title(title: str) -> str:
    return _INLINE_WS.sub(" ", unicodedata.normalize("NFC", title or "")).strip()
