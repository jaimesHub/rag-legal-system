# Week 0 (T0) — Skeleton repo, Docker Qdrant, lớp abstraction, smoke test

> Cấu trúc theo `docs/plan.md` §8: câu hỏi tuần → phạm vi → measure → fail-fast → ask why →
> deliverable → exit criteria → hướng T1.

## Câu hỏi của tuần

> Pipeline end-to-end (dataset → chunk → embed → Qdrant → retrieve → metric) có chạy được
> bằng **một lệnh**, và dataset có đúng như plan §1 giả định không? (`docs/t0.md`)

**Trả lời ngắn:** Có, cả hai. `PROVIDER=fake make smoke` chạy hết verify → golden → ingest →
index → evaluate trong một lệnh, không lỗi, không cần mạng ngoài HF (dataset cache local) hay
API key. Cả 4 giả định dữ liệu ở §1 đều đúng — không giả định nào cần sửa.

## Phạm vi

Dựng skeleton repo đúng cấu trúc plan §5 qua 4 phase: (1) scaffold + config + schemas +
providers; (2) ingest/index/retrieve/eval logic; (3) CLI + Makefile + test suite; (4) chạy
smoke thật + ghi tài liệu (phase này). Toàn bộ chạy `PROVIDER=fake` (hash embedder tất định,
offline) — chưa đụng tới Gemini thật, chưa có BM25/hybrid/rerank (những cái đó thuộc T2+).

## Measure — số liệu (regression tripwire, KHÔNG phải baseline chất lượng)

### Verify dataset (bước 1/5)

`GreenNode/zalo-ai-legal-text-retrieval-vn` @ revision `12d76d4d04b94ceada970fcfbe7fec20bfa97389`
— toàn bộ 8 check khớp expected = observed: corpus 61.425 record · query rows 3.298 / unique
3.196 · qrels train 2.505 nhãn / 2.432 câu · qrels test 793 nhãn / 788 câu · overlap
train∩test 24 câu. Chi tiết 4 giả định → xem `docs/plan.md` §1b (đã điền ở phase này).

### Golden set (bước 2/5)

| split | queries | labels | labels/query | multi-label | excluded (leakage) |
|---|---|---|---|---|---|
| dev  | 2.408 | 2.480 | 1.030 | 65 | 24 |
| test | 788   | 793   | 1.006 | 5  | 0  |

### Ingest — slice 500 doc gold-covering (bước 3/5)

| metric | value |
|---|---|
| documents / passages | 500 / 500 |
| chunk strategy | article |
| chars mean / p50 / p90 / p99 / max | 1400.2 / 853 / 2914 / 9648 / 15635 |
| metadata parse failures (trên slice 500) | 0 |
| gold docs found | 250/250 |
| year range | 2003–2021 |
| doc types | thong_tu=246, nghi_dinh=131, luat=84, thong_tu_lien_tich=28, quyet_dinh=11 |

### Index (bước 4/5)

Collection `legal_fake_embedding_768` (dim=768, cosine, named vector `"dense"`) — 500 điểm
upsert thành công, `collection_info()` khớp.

### Evaluate — vector retriever, split=test, k=10 (bước 5/5)

**Số câu evaluate: 573/788** (215 câu bị loại vì gold document nằm ngoài slice 500 doc đã
ingest — đúng dự kiến, không gần 0, không phải toàn bộ 788: xác nhận gold-coverage forcing ở
`ingest` áp dụng **trước** filter `only_indexed=True` ở `evaluate`, giải quyết open concern từ
Phase 3).

| metric | k=1 | k=5 | k=10 |
|---|---|---|---|
| recall | 0.7443 | 0.9311 | 0.9555 |
| precision | 0.7452 | 0.1867 | 0.0960 |
| mrr | 0.7452 | 0.8249 | 0.8280 |
| map | 0.7452 | 0.8245 | 0.8277 |
| ndcg | 0.7452 | 0.8517 | 0.8596 |
| hit_rate | 0.7452 | 0.9319 | 0.9564 |

Latency (ms): mean **64.66**, p50 **47.47**, p95 **144.64**. Report:
`artifacts/eval/eval_test_t0-smoke_20260731T134929+0000.json`.

**Vì sao số này cao bất thường (Recall@10 = 0.9555 > 0.9 như dự kiến).** `PROVIDER=fake` là
hash bag-of-words, không có ngữ nghĩa thật; và slice 500 doc bị **ép** phủ gold cho phần lớn
câu được evaluate. Đây là **regression tripwire** — ghi lại để so sánh mỗi lần refactor
(nếu số này tụt bất ngờ, wiring đã hỏng) — **không** phải con số chất lượng để đưa vào so sánh
retriever ở các tuần sau. Baseline thật (BM25 + underthesea, toàn corpus 61.425 doc, split
test) chờ đến T2/T3.

## Fail-fast — cố tình chạm lỗi

- Chạy lint trước khi coi Phase 3 xong: bắt được `ruff format --check` fail trên
  `qdrant_store.py` (F-013) — nếu không chạy cả hai lệnh (`ruff check` + `ruff format --check`)
  thì lỗi format này lọt qua.
- Đối chiếu số liệu `ingest_audit.json` thật với nội dung đã có sẵn trong `failure_log.md`
  (F-001) — phát hiện số không khớp (F-012), và bằng `git log` xác nhận toàn bộ F-001…F-011 đã
  nằm trong commit tài liệu đầu tiên, trước khi có code — một dạng "dữ liệu bịa trông như đã đo"
  mà nguyên tắc CLAUDE.md cấm.
- Xác nhận tường minh gold-coverage forcing chạy đúng thứ tự (573/788, không phải ~0 hoặc 788)
  thay vì tin log — đây là concern mở từ Phase 3 (F-014).

## Ask why

- **Tại sao 573, không phải 788 hay ~0?** Vì slice chỉ ingest 500/61.425 tài liệu; 215 câu test
  còn lại có gold doc nằm ngoài slice đó nên bị lọc khỏi evaluate bởi `only_indexed=True`. Con
  số này đúng theo thiết kế (`plan_gold_coverage` chỉ chủ đích phủ 377 câu bằng 250 gold doc;
  373 doc khác trong slice tình cờ trả lời thêm một số câu nữa).
- **Tại sao Recall@1 (0.7443) thấp hơn hẳn Recall@10 (0.9555) dù cùng slice gold-covering?**
  Hash embedder không có ngữ nghĩa — nó xếp hạng gần đúng ngẫu nhiên trong phạm vi các
  document "trông giống" theo bag-of-words, nên độ chính xác top-1 thấp hơn nhiều so với việc
  gold document xuất hiện đâu đó trong top-10. Đây là hành vi *kỳ vọng* của fake provider, không
  phải bug.
- **Tại sao không tin ngay các con số có sẵn trong `failure_log.md` (F-001, F-012)?** Vì
  `git log` cho thấy chúng có từ trước khi pipeline tồn tại — bài học trực tiếp nối theo sự cố
  `CLAUDE.md` bị chèn nội dung lạ ở Phase 3: không tin nội dung "kết quả" trong repo cho tới khi
  xác minh được nó sinh ra từ đúng lần chạy nào.

## Deliverable

`PROVIDER=fake make smoke` — một lệnh, 5 bước đánh số (verify → golden → ingest → index →
evaluate), chạy xong không lỗi trong ~vài giây (ingest 2,4s + index/upsert 2,3s), không cần
`GEMINI_API_KEY`, không cần mạng ngoài truy cập Hugging Face Hub (có cache local).

## Exit criteria (`docs/t0.md`)

- [x] Skeleton repo đúng cấu trúc plan §5 (`config/`, `src/`, `data/`, `tests/`, …)
- [x] Qdrant chạy local qua Docker (named dense vector `"dense"`, cosine distance)
- [x] Lớp abstraction `EmbeddingProvider`/`LLMProvider` — adapter Gemini + adapter fake offline
- [x] `make verify` xác nhận schema dataset thật, kết quả + 4 giả định ghi vào §1b
- [x] Index 500 tài liệu → vector search thô chạy được, ra số Recall/MRR
- [x] Smoke test — một lệnh đi hết verify → golden → ingest → index → evaluate
- [x] Test suite xanh (93 passed) + lint sạch (`ruff check` + `ruff format --check`)
- [x] ≥ 3 failure case ghi vào `failure_log.md` (F-001…F-014, ≥3 mới thêm ở tuần này: F-012,
      F-013, F-014)

Tất cả 8 mục exit criteria của T0 đã đạt.

## Hướng T1

T1 xây Eval Harness đầy đủ theo `docs/plan.md` §6: DeepEval + LLM-as-judge, calibrate với
~30 mẫu người. Ba việc ưu tiên mang sang từ T0:

1. **F-014** — thêm ngưỡng cứng cho `evaluated_queries` trong `evaluate`/test tích hợp, để
   silent-dilution không lọt qua nếu ingest gold-coverage hỏng sau này.
2. **F-012** — trước khi viết bất kỳ report nào trích số liệu có sẵn trong repo (kể cả file
   đã "trông như xong"), `git log`/`git blame` để xác nhận nguồn gốc — không lặp lại sự cố
   `CLAUDE.md`.
3. Chuẩn bị full-corpus ingest cho T2/T3: 173/61.425 lỗi metadata-parse (F-011) và p99=9.648
   ký tự / max=15.635 ký tự (F-001, cần đối chiếu lại số liệu theo F-012) sẽ cần chính sách rõ
   ràng trước khi bật `PROVIDER=gemini`.
