from __future__ import annotations

from src.ingest.chunk import chunk_document

ARTICLE_TEXT = (
    "1. Hàng năm trước mùa mưa lũ, Ủy ban nhân dân cấp xã phải tổ chức lực lượng "
    "tuần tra canh gác đê theo quy định.\n"
    "2. Lực lượng tuần tra canh gác đê được hưởng thù lao theo quy định của pháp luật "
    "hiện hành và do ngân sách địa phương chi trả.\n"
    "3. Ủy ban nhân dân cấp huyện có trách nhiệm kiểm tra việc tổ chức lực lượng."
)


def test_article_strategy_keeps_one_passage_per_document(settings):
    settings.chunk_strategy = "article"
    passages = chunk_document(
        "01/2009/tt-bnn+2", "Điều 2. Tổ chức lực lượng", ARTICLE_TEXT, settings
    )
    assert len(passages) == 1
    assert passages[0].passage_id == passages[0].doc_id == "01/2009/tt-bnn+2"


def test_embed_text_includes_the_title(settings):
    """The article heading is often the strongest retrieval signal."""
    settings.chunk_strategy = "article"
    passage = chunk_document(
        "01/2009/tt-bnn+2", "Điều 2. Tổ chức lực lượng", ARTICLE_TEXT, settings
    )[0]
    assert passage.embed_text.startswith("Điều 2. Tổ chức lực lượng")
    assert "Hàng năm" in passage.embed_text


def test_khoan_strategy_splits_into_khoan(settings):
    settings.chunk_strategy = "khoan"
    settings.chunk_min_chars = 20
    passages = chunk_document(
        "01/2009/tt-bnn+2", "Điều 2. Tổ chức lực lượng", ARTICLE_TEXT, settings
    )
    assert len(passages) == 3
    assert [p.metadata.khoan_no for p in passages] == ["1", "2", "3"]


def test_khoan_chunks_keep_the_parent_doc_id(settings):
    """Golden labels point at the Điều, so doc_id must not become the chunk id."""
    settings.chunk_strategy = "khoan"
    settings.chunk_min_chars = 20
    passages = chunk_document(
        "01/2009/tt-bnn+2", "Điều 2. Tổ chức lực lượng", ARTICLE_TEXT, settings
    )
    assert {p.doc_id for p in passages} == {"01/2009/tt-bnn+2"}
    assert len({p.passage_id for p in passages}) == 3


def test_khoan_chunk_titles_name_the_khoan(settings):
    settings.chunk_strategy = "khoan"
    settings.chunk_min_chars = 20
    passages = chunk_document("01/2009/tt-bnn+2", "Điều 2. Tổ chức", ARTICLE_TEXT, settings)
    assert passages[0].title.endswith("Khoản 1")


def test_short_khoan_are_merged_into_the_previous_chunk(settings):
    settings.chunk_strategy = "khoan"
    settings.chunk_min_chars = 200
    passages = chunk_document("01/2009/tt-bnn+2", "Điều 2. Tổ chức", ARTICLE_TEXT, settings)
    # Every segment is under 200 chars, so they all fold into one.
    assert len(passages) == 1


def test_oversized_khoan_is_split_on_diem(settings):
    settings.chunk_strategy = "khoan"
    settings.chunk_min_chars = 0
    settings.chunk_max_chars = 120
    text = (
        "1. Các trường hợp sau đây bị xử phạt:\n"
        "a) " + "vi phạm quy định về tốc độ khi điều khiển phương tiện " * 3 + "\n"
        "b) " + "vi phạm quy định về nồng độ cồn khi điều khiển phương tiện " * 3
    )
    passages = chunk_document("01/2020/nđ-cp+5", "Điều 5. Xử phạt", text, settings)
    assert len(passages) >= 2
    assert all(p.doc_id == "01/2020/nđ-cp+5" for p in passages)


def test_text_without_khoan_markers_yields_single_chunk(settings):
    settings.chunk_strategy = "khoan"
    passages = chunk_document(
        "01/2009/tt-bnn+1", "Điều 1. Phạm vi", "Thông tư này hướng dẫn.", settings
    )
    assert len(passages) == 1


def test_empty_text_still_produces_a_passage(settings):
    settings.chunk_strategy = "khoan"
    passages = chunk_document("01/2009/tt-bnn+9", "Điều 9. Hiệu lực", "", settings)
    assert len(passages) == 1
    assert passages[0].embed_text == "Điều 9. Hiệu lực"
