# Phase 4 (T0 bước 17–19) — Báo cáo (phase cuối của T0)

**Đóng gói T0** bằng smoke run thực tế, ghi lại failure case tuần, viết production report, và cập nhật plan với số liệu thật từ `make verify`. Đây là phase cuối khép lại T0.

---

## Bước 17 — Smoke run offline (`PROVIDER=fake make smoke`)

Chạy hết pipeline 5 bước (verify → golden → ingest → index → evaluate) trong môi trường offline, không cần API key hay mạng.

**Kết quả:**
- ✅ Tất cả 5 bước không lỗi
- **573/788 câu test được eval** — 215 câu bị lọc vì tài liệu gốc nằm ngoài slice 500 documents
  - Con số này hợp lý, phù hợp với quyết định áp dụng gold-coverage trước bộ lọc eval-time (giải quyết concern từ Phase 3)
- **Regression tripwire** (fake embedder, slice gold-covering):

| Metric | k=1 | k=5 | k=10 |
|--------|-----|-----|------|
| Recall | 0.7443 | 0.9311 | 0.9555 |
| Precision | 0.7452 | 0.1867 | 0.0960 |
| MRR | 0.7452 | 0.8249 | 0.8280 |
| MAP | 0.7452 | 0.8245 | 0.8277 |
| nDCG | 0.7452 | 0.8517 | 0.8596 |

**Latency (ms):** mean 64.66, p50 47.47, p95 144.64

⚠️ Số này **KHÔNG phải baseline chất lượng** (embedder hash + slice small) — chỉ là mốc phát hiện regression khi refactor về sau.

---

## Bước 18 — failure_log.md

Thêm 3 entry mới của tuần:
- **F-012**: Documentation integrity — các phần `failure_log.md` không sync với implementation
- **F-013**: Lint gap — ruff format chưa tự động chạy
- **F-014**: Silent dilution risk — `evaluated_queries` không có ngưỡng cứng khi lọc

---

## ⚠️ Issue phát hiện & xử lý: Data integrity

### Vấn đề
Khi chạy `make verify`, phát hiện **`failure_log.md` (commit 5aeade9)** phần lớn **copy từ dự án mẫu** mà chưa adapt cho bộ dataset thật:

- **F-001**: Ghi số p50/p90/p99/max = `888/3.515/9.954/51.862` ❌ không khớp số đo thật (853/2.914/9.648/15.635)
- **F-004, F-007–F-010**: Mô tả kết quả T2/BM25 và trỏ tới file chưa tồn tại (`src/retrieve/bm25.py`, `notebooks/02_lexical_search.ipynb`)

**Vi phạm nguyên tắc lõi:** `failure_log.md` không được tự điền số liệu chưa đo đạc thực tế.

### Quyết định & Thực hiện
Main agent kiểm chứng độc lập (git log + so số thật) → xác nhận cơ sở → hỏi hướng xử lý.  
**Quyết định**: _Xoá entry sai lệch từ dự án mẫu._

Spawn Sonnet subagent thực hiện:
1. ✅ Xoá hẳn F-004/F-007/F-008/F-009/F-010 (chỉ có mô tả, không căn cứ dự án này)
2. ✅ Viết lại F-001 bằng số đo thật (853/2.914/9.648/15.635), bỏ suy diễn không có trong audit
3. ✅ Chuyển F-012 thành bản ghi "✅ Resolved" với provenance
4. ✅ Sửa 1 ref treo ở F-014 và 1 ref treo ở `reports/week0.md`
5. ✅ Xoá file lạ `failure_log_template.md` (425 dòng backup không cần, do fix agent tạo nhưng không khai báo)

**Kết quả:** `failure_log.md` giữ nguyên ID (F-001/002/003/005/006/011/012/013/014), bản gốc sai vẫn khôi phục được từ commit 5aeade9 để audit.

---

## Bước 19 — reports/week0.md + Cập nhật plan.md

### reports/week0.md (141 dòng)
- Theo cấu trúc plan §8: câu hỏi tuần → phạm vi → measure → fail-fast → ask why → deliverable → exit criteria (đều ✅) → hướng T1
- Trung thực: số metric là tripwire (fake embedder), baseline chất lượng thật chờ T2/T3 khi dùng Gemini thật

### docs/plan.md §1b — Điều kiện ban đầu (filled with real data)
| Giả định | Giá trị thật |
|---------|-------------|
| Chunk level | Điều (Article) — có sẵn ✅ |
| Nhãn/câu hỏi (test) | mean 1.006, multi-label 5/788 (0.6%) |
| Nhãn/câu hỏi (train) | mean 1.03, multi-label 66/2.432 (2.7%) |
| Leakage (query overlap) | 24 |
| Duplicate `_id` trong corpus | 102 |
| Corpus size | 61,425 documents |
| Test split | 788 queries |
| Dataset revision | 12d76d4d |

Không giả định nào cần sửa.

### docs/plan.md §3 — T0 Status
- ⬜ TODO → **✅ [week0](../reports/week0.md)** (link local; không bịa URL GitHub vì chưa có remote)

---

## Kết quả verify cuối (tự chạy)

| Kiểm tra | Kết quả |
|---------|---------|
| `PROVIDER=fake make smoke` | ✅ 5 bước OK, 573/788 eval, Recall@10 = 0.9555 (tripwire) |
| `uv run pytest -q` | ✅ 93 passed |
| `make lint` | ✅ PASS (ruff format + check) |
| `git status` | M docs/plan.md, M failure_log.md, ?? reports/week0.md |
| Ref treo (F-004/007–010) | ✅ Không còn |

---

## T0 hoàn tất — Exit criteria (t0.md)

- [x] **Skeleton repo** — cấu trúc đúng plan §5, không hard-code path
- [x] **Qdrant Docker** — named dense vector, cosine similarity
- [x] **Lớp abstraction** — EmbeddingProvider + LLMProvider (Gemini + fake offline)
- [x] **make verify** — xác nhận schema & counts dataset thật → §1b điền số thật
- [x] **Index → Search** — 500 docs → vector search, Recall/MRR metric
- [x] **Smoke test** — một lệnh đơn: `verify→golden→ingest→index→evaluate`
- [x] **Test xanh** — 93 passed, lint sạch
- [x] **≥3 failure case** — F-012 (documentation), F-013 (lint), F-014 (silent dilution)

---

## Bước tiếp → T1

**T1: Evaluating Search Systems**
- Golden set + dev/test split đã có
- Thêm DeepEval + LLM-as-judge (LLM ranking accuracy)
- Bật Gemini thật → có khả năng chạm **F-001** (Điều dài vượt token window)
  - Cần chính sách truncation hoặc sub-chunk trước khi pass tới judge

**Baseline chất lượng** sẽ từ T2/T3 (BM25 + Underthesea trên toàn corpus).
