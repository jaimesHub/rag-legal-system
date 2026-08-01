# Phase 2 (T0 bước 7–13) — Báo cáo

**Phạm vi:** Hoàn tất bước 7–13 trong `docs/week0/t0.md` — biến các stub Phase 1 thành logic thật cho toàn bộ pipeline: `ingest → index → retrieve → eval`.

**Câu hỏi tuần (T0):** pipeline end-to-end (dataset → chunk → embed → Qdrant → retrieve → metric) có chạy được không, và dataset có đúng như plan §1 giả định không? → Phase 2 trả lời phần lớn: pipeline chạy được offline (`PROVIDER=fake`), và 4 giả định dữ liệu đã được xác nhận bằng số thật.

> **Lưu ý:** verify thực hiện bằng cách gọi trực tiếp Python + pytest, vì CLI (`src/cli.py`) và các target `make verify/golden/ingest/index/search` thuộc bước 14–15 (Phase 3), chưa tồn tại. Embedding chạy `PROVIDER=fake` (offline, không tốn API); Qdrant chạy qua Docker.

---

## Modules đã implement

| Module | Nội dung chính |
|---|---|
| `src/ingest/loader.py` | `_download`/`iter_corpus`/`load_queries`/`load_qrels`/`verify_dataset`; đọc JSONL gốc trên HF (pin revision), nhận cả khoá `_id` và `id`; hằng số `EXPECTED` |
| `src/ingest/clean.py` | NFC normalize + dọn whitespace, giữ newline |
| `src/ingest/metadata.py` | `parse_corpus_id`, `parse_title`, `build_metadata`; parse **phòng thủ** (`parse_ok=False`, không raise); special-case Quốc hội |
| `src/ingest/chunk.py` | `chunk_document` với chiến lược `article` / `khoan`; `doc_id` luôn trỏ về Điều cha |
| `src/eval/golden.py` | `build_golden`/`load_golden`; leakage guard (loại overlap khỏi dev, giữ trong test) |
| `src/ingest/pipeline.py` | `plan_gold_coverage`, `build_passages`, `write/load_passages`, `IngestAudit` (phân phối ký tự p50/p90/p99/max) |
| `src/index/qdrant_store.py` | `QdrantStore` — named dense vector `"dense"`, point id UUID5, payload index cho field T5, cosine distance |
| `src/retrieve/base.py` + `vector.py` | `SearchHit`, `dedupe_by_doc`, `VectorRetriever` (oversample k×3, task_type `RETRIEVAL_QUERY`) |
| `src/eval/metrics.py` + `harness.py` | `metrics_at_k`/`aggregate`; `evaluate_retriever`/`EvalReport`/`save/load/list_reports` (đo per-query + latency + provenance) |

**Khác biệt so với dự án mẫu:** schema `Passage` (Phase 1, đã commit) không có field `n_chars`, nên `pipeline.py` tính thống kê độ dài từ `len(passage.embed_text)` tại chỗ thay vì lưu per-passage — cùng output audit, không phải đổi schema.

---

## Bước 7 — Verify dataset (tải thật, revision `12d76d4d…`)

Toàn bộ 8 check **pass** (`all_ok: true`) — expected khớp observed tuyệt đối:

| Chỉ số | Expected = Observed |
|---|---|
| corpus records | 61,425 |
| query rows / unique | 3,298 / 3,196 |
| qrels train labels / queries | 2,505 / 2,432 |
| qrels test labels / queries | 793 / 788 |
| overlap query id (train∩test) | 24 |

### 4 giả định dữ liệu (§1b) — số thật
1. **Corpus đã chunk sẵn ở mức Điều?** → **Có** (mẫu `01/2009/tt-bnn+1..5`, mỗi record một Điều).
2. **Trung bình nhãn/câu?** → hầu như single-label. Test: mean **1.006**, chỉ **5/788** multi-label (0.6%). Train: mean **1.03**, **66/2432** multi-label (2.7%).
3. **Leakage?** → **24** query id xuất hiện ở cả train và test qrels.
4. **Dòng trùng `_id` trong queries.jsonl?** → **102**.

> Đây là nguyên liệu cho `docs/plan.md` §1b, nhưng **chưa** điền vào plan — việc cập nhật §1b + đổi trạng thái T0 thuộc Phase 4 (báo cáo T0), theo đúng t0.md bước 19.

---

## Golden set (bước 9)

- **dev: 2,408 câu** (24 câu leakage bị loại, mean 1.03 nhãn/câu, 65 multi-label)
- **test: 788 câu** (mean 1.006 nhãn/câu, 5 multi-label)
- 102 dòng query trùng `_id` bị dedupe
- Kiểm chứng: cả 24 id overlap **vắng mặt trong dev** nhưng **còn nguyên trong test** ✅
- Artifacts: `data/golden/{dev,test}.jsonl` + `manifest.json`

---

## Ingest audit — slice 500 doc gold-covering (bước 10)

- `plan_gold_coverage` ép **250 gold doc** phủ **377 test query** vào slice; `gold_documents_found == 250` khớp đúng.
- Phân phối độ dài ký tự: mean 1400, p50 853, p90 2914, **p99 9,648, max 15,635** → vượt xa cửa sổ token embedding điển hình ⇒ **xác nhận bẫy #5**: Điều dài sẽ bị cắt âm thầm khi bật Gemini thật (T1/T3).
- `metadata_parse_failures = 0` trên slice — **nhưng** chạy parser trên **toàn corpus 61,425 record** phát hiện **173 lỗi (0.28%)** ⇒ **xác nhận bẫy #4**: slice nhỏ giấu hẳn lớp lỗi này.

---

## Index Qdrant (bước 11)

- Docker ban đầu chưa có container → `make up`, pull `qdrant/qdrant:v1.12.4`, chờ `/healthz`.
- Index 500 passage (fake-embedded) vào collection **`legal_fake_embedding_128`** (đúng slug fake-riêng, **không** lẫn `legal_gemini-embedding-001_768` — bẫy #2). `count()==500`, `collection_info()` khớp.
- Chạy lại upsert: `count()` vẫn 500 → **không trùng**, xác nhận point id UUID5 tất định.
- Qdrant **để chạy tiếp** cho Phase 3.
- ⚠️ Cảnh báo không chặn: `qdrant-client` 1.18.0 vs server image 1.12.4 → `UserWarning` mỗi call. Không lỗi chức năng, nhưng nên pin đồng bộ client/server.

---

## Vector retrieval + eval nhỏ (bước 12/13)

- **Sanity:** score giảm dần, **không trùng `doc_id`**; `k=10000` trên collection 500 điểm trả đủ 500, không crash; query vô nghĩa vẫn trả score cosine "trông bình thường" (~0.22) — hành vi ANN đúng dự kiến (đây là loại thứ LLM-judge ở T1 cần bắt, không phải bug — bẫy #3).
- **Eval nhỏ (5 query):** `n_queries=5`, recall@10=1.0, mrr@10=0.9, latency mean 72.6ms / p50 72.0 / p95 112.7.

> ⚠️ Đây là **regression tripwire tất lạc quan** trên slice gold-covering + fake embedder — **KHÔNG phải baseline chất lượng**. Số baseline thật chờ full-corpus + Gemini ở T2/T3.

---

## Test & Lint

- Thêm `tests/unit/{test_clean, test_metadata, test_chunk, test_golden, test_metrics, test_retrieve_base, test_harness}.py`
- `uv run pytest tests/unit -q` → **52 passed**
- `uv run ruff check src config tests` → **sạch**
- Xác nhận cô lập test: chạy lại pytest không sinh file lạ dưới `data/` (fixture `base_dir=tmp_path` chứa mọi ghi) — **tránh được bẫy #1**

---

## Concerns bàn giao Phase 3
- **Version mismatch** qdrant-client 1.18.0 vs server v1.12.4 — cosmetic hôm nay, nên pin đồng bộ sớm.
- **173 lỗi metadata-parse** ở quy mô full corpus (0.28%) — vô hình trong mọi smoke 500 doc; ingest full (T3) cần assert không regress âm thầm.
- **p99 độ dài 9,648 ký tự** sẽ chạm giới hạn token embedding thật — Phase 3/T1 cần chính sách truncation/sub-chunk trước khi đổi `PROVIDER=gemini`.

---

## Bước tiếp theo → Phase 3 (t0.md bước 14–16)
1. `src/cli.py` — Typer app ráp toàn bộ thành lệnh (`verify-dataset`, `build-golden`, `ingest`, `index`, `search`, `evaluate`, `smoke`)
2. Makefile — target 1-1 với CLI (`verify/golden/ingest/index/search/eval/smoke/test/lint`)
3. `tests/` — bổ sung test còn thiếu + `integration/test_offline_smoke.py`

Sau đó Phase 4 (bước 17–19): chạy `PROVIDER=fake make smoke`, ghi `failure_log.md` (≥3 case), viết `reports/week0.md` + cập nhật `docs/plan.md` §1b/§3.
