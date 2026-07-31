"""Parse corpus ids and titles into `src.schemas.LegalMetadata`.

Corpus ids look like ``01/2009/tt-bnn+1`` = <number>/<year>/<code>+<article index>.
The code carries both document type and issuing body (``tt-bnn`` = Thông tư of
Bộ Nông nghiệp), except for National Assembly instruments, which encode the
assembly term instead of an issuer (``59/2020/qh14`` — "qh14" is Quốc hội khóa 14,
not an issuing body).

Parsing is defensive: anything that doesn't match the expected shape sets
``parse_ok=False`` and is counted in the ingest audit, never raised — one
malformed id must not abort an entire ingest run.
"""

from __future__ import annotations

import re

from src.schemas import LegalMetadata

_TITLE_RE = re.compile(r"^\s*Điều\s+(\d+[a-zA-Zđ]?)\s*[.:\-]?\s*(.*)$", re.IGNORECASE)
_QH_RE = re.compile(r"^qh\d*$")

# Normalised type -> human label. Keys are the code prefix before the first "-".
_DOC_TYPES: dict[str, tuple[str, str]] = {
    "l": ("luat", "Luật"),
    "qh": ("luat", "Luật / Nghị quyết Quốc hội"),
    "nđ": ("nghi_dinh", "Nghị định"),
    "nd": ("nghi_dinh", "Nghị định"),
    "tt": ("thong_tu", "Thông tư"),
    "ttlt": ("thong_tu_lien_tich", "Thông tư liên tịch"),
    "qđ": ("quyet_dinh", "Quyết định"),
    "qd": ("quyet_dinh", "Quyết định"),
    "nq": ("nghi_quyet", "Nghị quyết"),
    "ct": ("chi_thi", "Chỉ thị"),
    "pl": ("phap_lenh", "Pháp lệnh"),
    "vbhn": ("van_ban_hop_nhat", "Văn bản hợp nhất"),
    "sl": ("sac_lenh", "Sắc lệnh"),
}


def parse_corpus_id(corpus_id: str) -> LegalMetadata:
    """Split a corpus id into document key and article index. Never raises."""
    doc_key, sep, tail = corpus_id.rpartition("+")
    if not sep:
        # No "+<article>" separator — treat the whole id as the document key.
        return LegalMetadata(doc_key=corpus_id, parse_ok=False)

    article_index = int(tail) if tail.isdigit() else None
    meta = LegalMetadata(
        doc_key=doc_key,
        article_index=article_index,
        parse_ok=article_index is not None,
    )

    parts = doc_key.split("/")
    if len(parts) != 3:
        meta.parse_ok = False
        return meta

    number, year_raw, code = parts
    meta.doc_number = number
    meta.doc_code = code
    if year_raw.isdigit():
        year = int(year_raw)
        # Sanity window: these are Vietnamese legal instruments, not arbitrary ints.
        meta.year = year if 1945 <= year <= 2100 else None
    if meta.year is None:
        meta.parse_ok = False

    prefix, _, issuer = code.partition("-")
    if _QH_RE.match(prefix):
        # 59/2020/qh14 — "14" is the National Assembly term, not an issuer.
        meta.doc_type, meta.doc_type_label = _DOC_TYPES["qh"]
        meta.issuer = "qh"
    elif prefix in _DOC_TYPES:
        meta.doc_type, meta.doc_type_label = _DOC_TYPES[prefix]
        meta.issuer = issuer or None
    else:
        meta.issuer = issuer or None
        meta.parse_ok = False

    return meta


def parse_title(title: str, meta: LegalMetadata) -> LegalMetadata:
    """Fill article number and heading from a title like ``Điều 15. Xử phạt...``."""
    match = _TITLE_RE.match(title or "")
    if not match:
        meta.article_heading = (title or "").strip() or None
        return meta
    meta.article_no = match.group(1)
    meta.article_heading = match.group(2).strip() or None
    return meta


def build_metadata(corpus_id: str, title: str) -> LegalMetadata:
    return parse_title(title, parse_corpus_id(corpus_id))
