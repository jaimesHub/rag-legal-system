"""Split a corpus record into indexable `src.schemas.Passage` chunks.

Finding from the Phase 2 dataset audit (docs/t0.md step 7): this corpus is
**already chunked at Điều level** — one record per article, and golden labels
point at exactly those records. So the default strategy is ``"article"``: keep
the shipped unit as-is, because splitting finer would mean a retrieved chunk no
longer maps 1:1 to a labelled unit.

The ``"khoan"`` strategy sub-splits each Điều into its Khoản (and, if a Khoản is
still too long, its Điểm or a hard character cut), but ``doc_id`` always points
back to the parent Điều so metrics stay comparable between the two strategies.
"""

from __future__ import annotations

import re

from config.settings import Settings
from src.ingest.clean import clean_text, clean_title
from src.ingest.metadata import build_metadata
from src.schemas import Passage

# Khoản markers: "1." / "2." at the start of the text or of a line.
_KHOAN_RE = re.compile(r"(?:^|\n)\s*(\d{1,2})[.)]\s+")
# Điểm markers: "a)" / "b)" — used only to break up an oversized Khoản.
_DIEM_RE = re.compile(r"(?:^|\n)\s*([a-zđ])\)\s+")


def embed_text(title: str, body: str) -> str:
    """What actually gets embedded: title + content.

    The title carries the article heading ("Điều 15. Xử phạt...") which is often
    the strongest signal for a lookup-style question, so it is prepended rather
    than kept as metadata only.
    """
    title = title.strip()
    body = body.strip()
    if title and body:
        return f"{title}\n{body}"
    return title or body


def _split_on(pattern: re.Pattern[str], text: str) -> list[tuple[str | None, str]]:
    """Split text on a marker, returning (marker, segment) pairs.

    Any text before the first marker is returned with marker ``None``.
    """
    matches = list(pattern.finditer(text))
    if not matches:
        return [(None, text)]

    segments: list[tuple[str | None, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        segments.append((None, preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if body:
            segments.append((match.group(1), body))
    return segments


def _merge_short(
    segments: list[tuple[str | None, str]], min_chars: int
) -> list[tuple[str | None, str]]:
    """Fold segments below ``min_chars`` into the previous one.

    A bare "1. Như sau:" carries no retrievable content on its own; leaving it
    as its own chunk just adds noise to the index.
    """
    if not segments:
        return []
    merged: list[tuple[str | None, str]] = [segments[0]]
    for marker, body in segments[1:]:
        if len(body) < min_chars:
            prev_marker, prev_body = merged[-1]
            merged[-1] = (prev_marker, f"{prev_body}\n{marker or ''} {body}".strip())
        else:
            merged.append((marker, body))
    return merged


def chunk_document(
    corpus_id: str,
    title: str,
    text: str,
    settings: Settings,
) -> list[Passage]:
    """Turn one corpus record into one or more passages."""
    clean_title_ = clean_title(title)
    body = clean_text(text)
    meta = build_metadata(corpus_id, clean_title_)

    if settings.chunk_strategy == "article" or not body:
        return [
            Passage(
                passage_id=corpus_id,
                doc_id=corpus_id,
                title=clean_title_,
                text=body,
                embed_text=embed_text(clean_title_, body),
                metadata=meta,
            )
        ]

    segments = _merge_short(_split_on(_KHOAN_RE, body), settings.chunk_min_chars)

    # Break up any segment that is still too long for the embedding window.
    expanded: list[tuple[str | None, str]] = []
    for marker, segment in segments:
        if len(segment) <= settings.chunk_max_chars:
            expanded.append((marker, segment))
            continue
        diem_parts = _split_on(_DIEM_RE, segment)
        if len(diem_parts) == 1:
            # No Điểm structure to exploit — hard-wrap on the character budget.
            for start in range(0, len(segment), settings.chunk_max_chars):
                expanded.append((marker, segment[start : start + settings.chunk_max_chars]))
        else:
            head = diem_parts[0][1] if diem_parts[0][0] is None else ""
            for diem_marker, diem_body in diem_parts:
                if diem_marker is None:
                    continue
                merged_body = f"{head}\n{diem_marker}) {diem_body}".strip() if head else diem_body
                expanded.append((marker, merged_body))

    passages: list[Passage] = []
    for position, (marker, segment) in enumerate(expanded, start=1):
        chunk_meta = meta.model_copy(update={"khoan_no": marker})
        prefix = f"{clean_title_} — Khoản {marker}" if marker else clean_title_
        passages.append(
            Passage(
                # doc_id stays the parent article so golden labels still match.
                passage_id=f"{corpus_id}#k{position}",
                doc_id=corpus_id,
                title=prefix,
                text=segment,
                embed_text=embed_text(prefix, segment),
                metadata=chunk_meta,
            )
        )
    return passages
