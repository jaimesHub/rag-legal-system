# Phase 3 (T0 bước 14–16) — Báo cáo

## Tổng quát

Hoàn tất bước 14–16 trong `docs/week0/t0.md` — ráp toàn bộ logic Phase 2 thành CLI (Typer) + Makefile + test suite đầy đủ. Phạm vi **CHỈ Phase 3**; chưa chạy `make smoke` chính thức (bước 17, thuộc Phase 4).

---

## Chi tiết triển khai

### Bước 14 — `src/cli.py` (Typer app)

- **8 lệnh T0:** `fetch`, `verify-dataset`, `build-golden`, `ingest` (--limit, default 500), `index` (--limit, --recreate), `search` (--query/-q, --k), `evaluate` (--split, --retriever, --k, --label; mặc định --split test), `smoke`
- **Không có lệnh T2:** tokens, sweep, compare, view-eval bị loại trừ ở Phase 3
- **`smoke` = deliverable T0:** gọi tuần tự `verify-dataset` → `build-golden` → `ingest` → `index` → `evaluate(retriever="vector", label="t0-smoke")` trong 1 lệnh, 5 bước đánh số
- **Xử lý provider:**
  - `_embedder(settings)` resolve via registry
  - Báo lỗi rõ ràng (không traceback) khi `provider=gemini` mà thiếu API key
  - `_run_context` gom config cho provenance
  - Dùng `rich` cho bảng kết quả

### Bước 15 — `Makefile`

| Phân loại | Lệnh | Mô tả |
|---|---|---|
| **Docker** | `up`, `down`, `logs` | Bật/tắt/xem Qdrant (có sẵn Phase 1) |
| **Dữ liệu** | `verify`, `golden`, `ingest`, `index` | Kiểm tra, golden set, xử lý corpus, tạo vector |
| **Tra cứu** | `search` | Ad-hoc query |
| **Đánh giá** | `eval`, `smoke` | Tính metric, offline smoke test |
| **DevOps** | `sync`, `test`, `lint`, `fmt`, `clean`, `help` | Dependency, test, format, dọn dẹp, trợ giúp |

**Biến:**
- `LIMIT` mặc định 500 cho ingest/smoke; `LIMIT=0` = full corpus (T2+)

**Nội dung `clean` target:**
- Xoá `data/processed` + artifacts + cache
- **KHÔNG xoá** `data/raw/` hay `data/golden/`

### Bước 16 — Test suite

**Test mới:**

| File | Test | Mô tả |
|---|---|---|
| `tests/unit/test_settings.py` | 12 test | Derive collection name, fake tách collection riêng |
| `tests/unit/test_providers.py` | 20 test | Fake provider tất định, đúng embedding dim |
| `tests/unit/test_pipeline.py` | 11 test | Slice gold-covering phủ đúng số query |
| `tests/integration/test_offline_smoke.py` | 8 test | Smoke offline toàn bộ, không cần mạng/Docker |

**Integration smoke (offline hoàn toàn):**
- Monkeypatch 3 hàm chạm mạng: `iter_corpus`, `load_queries`, `load_qrels` ở mọi module import chúng (loader, golden, pipeline)
- `QdrantClient(location=":memory:")` — không cần Docker
- Không tốn API quota

**Kết quả:**
```
52 test cũ (Phase 2) + 41 test mới = 93 passed
```

---

## Kết quả verify (đã chạy thật)

| Kiểm tra | Kết quả | Ghi chú |
|---|---|---|
| `python -m src.cli --help` | ✓ | Đúng 8 lệnh T0, không có lệnh T2 |
| `make help` | ✓ | Bảng: help up down logs sync fetch verify golden ingest index search eval smoke test lint fmt clean |
| `uv run pytest -q` | ✓ | 93 passed |
| `ruff check` | ✓ | Sạch |
| `make lint` | ✓ | Exit 0 (sau fix) |
| Test isolation | ✓ | Không sinh file lạ dưới `data/` (fixture base_dir=tmp_path) |

---

## Issue phát hiện & đã fix

### Lỗi format code (Phase 2)

**Triệu chứng:**
- `make lint` fail lần đầu với báo: `ruff format --check` tìm thấy `src/index/qdrant_store.py` (Phase 2) chưa format
- Chi tiết: 1 lời gọi `warnings.filterwarnings(...)` bị tách 3 dòng

**Xử lý:**
- Spawn Sonnet subagent để chạy `ruff format`
- Gộp về 1 dòng (thuần format, không đổi logic)
- Sau fix: `make lint` → exit 0, `pytest` vẫn 93 passed

### Sự cố CLAUDE.md (ghi nhận, chưa rõ nguyên nhân)

- Giữa lúc làm, `CLAUDE.md` trên đĩa xuất hiện 2 dòng nội dung lạ mà subagent không viết
- Xử lý: Coi là untrusted (protocol: không agent nào được sửa CLAUDE.md)
- Revert: `git checkout -- CLAUDE.md`
- Verify: `git diff HEAD -- CLAUDE.md` trống → không còn nội dung lạ
- **Trạng thái:** Đã dọn sạch, không ảnh hưởng deliverable

---

## Điều chỉnh khi ráp CLI

### Xử lý provider & retriever

- `verify-dataset` gọi thẳng `loader.verify_dataset(settings)` (Phase 2 đủ check)
- `evaluate` không có option BM25 (k1/b/tokenizer) vì chưa có BM25 ở T0
- `--retriever` chỉ nhận `"vector"`, thoát sạch với giá trị khác
- `evaluate` lọc golden về các câu có gold `doc_id` nằm trong tập đã index (`only_indexed=True`)

### Gold coverage filtering

- Slice 500 gold-covering không bị pha loãng bởi câu ngoài phạm vi index
- `smoke` gọi trực tiếp các hàm command tuần tự (không qua subprocess)

---

## Concerns bàn giao → Phase 4

1. **Gold coverage verification:** `PROVIDER=fake make smoke` cần xác nhận việc ép gold-coverage trong ingest thực sự áp dụng **TRƯỚC** bộ lọc eval-time đọc golden test split. Phase 3 mới chứng minh từng lớp offline riêng lẻ (unit + synthetic integration), chưa chạy full 500-doc trên corpus thật end-to-end.

2. **Qdrant health check:** Kiểm tra Qdrant còn chạy (`make up`) trước khi chạy smoke.

---

## Bước tiếp theo → Phase 4 (t0.md bước 17–19)

1. **`PROVIDER=fake make smoke`**
   - Chạy chính thức, ghi lại con số tripwire (regression, KHÔNG phải baseline chất lượng)

2. **`failure_log.md`**
   - Ghi ≥3 failure case từ Phase 3:
     - F-XXX: Giới hạn token với Điều dài
     - F-XXX: Leakage/duplicate giữa split
     - F-XXX: Lỗi harness gặp phải

3. **`reports/week0.md` + update `docs/plan.md`**
   - §1b: Cập nhật 4 giả định (sau khi có số thật từ smoke)
   - §3: Mark T0 → DONE
   - `reports/week0.md`: Số liệu + lift so baseline + ≥3 failure + "tại sao"
