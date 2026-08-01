# Week 0 (T0) — Skeleton repo, Docker Qdrant, lớp abstraction, smoke test

> Cấu trúc theo `docs/plan.md` §8: câu hỏi tuần → phạm vi → measure → fail-fast → ask why →
> deliverable → exit criteria → hướng T1.

## Câu hỏi của tuần

> Pipeline end-to-end (dataset → chunk → embed → Qdrant → retrieve → metric) có chạy được
> bằng **một lệnh**, và dataset có đúng như plan §1 giả định không? (`docs/week0/t0.md`)

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

## Exit criteria (`docs/week0/t0.md`)

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

## So với dự án mẫu (T0)

> Nguồn số mẫu: `docs/sample-baselines.yaml` (chép tay từ report đã commit của mẫu).
> Hàng metric chỉ hiện khi cùng cấu hình (revision + split=test + full corpus + 788 câu);
> nếu không, đánh ➖ kèm lý do. Không bịa số. Sinh bởi
> `make compare-sample WEEK=0 CS_ARGS="--emit-md --json artifacts/compare_sample/week0.json"`,
> chạy lại sau khi thêm mục này để xác nhận trục 4 lật ✅ (xem cột "Bằng chứng").

### Scorecard 7 trục

| Trục | Trạng thái | Bằng chứng |
|------|:----------:|------------|
| 1. structure | ✅ | src 25 files vs mẫu 29; không thiếu module tuần; mẫu có thêm `src/retrieve/bm25.py`, `src/retrieve/splade.py`, `src/ingest/tokenize.py`, `src/rank`, `src/generate`, `dashboard`, `notebooks` — mẫu đã tới T2+, đúng dự kiến. |
| 2. tests | ✅ (người xác nhận) | Tool đếm 🟡 (12 files / 115 funcs, mẫu 15/179) vì chỉ đếm không chạy. Người xác nhận: `uv run pytest -q` → **115 passed**, 0 failed — xanh thật tại thời điểm ghi (2026-08-01). |
| 3. metrics | ➖ | Số T0 là tripwire fake-embedder trên slice 500-doc gold-covering (573/788 câu evaluate) — không phải số chất lượng, không so được với mẫu (mẫu benchmark full-corpus 61.425 doc / 788 câu). Head-to-head thật bắt đầu từ T2 (BM25/underthesea). Đây là thiết kế, không phải thiếu sót. |
| 4. docs | ✅ (sau khi thêm mục này) | Mục "So với dự án mẫu (T0)" này chính là phần còn thiếu — trước khi thêm, tool báo 🟡 vì `reports/week0.md` chưa có chuỗi con "So với dự án mẫu". Sau khi thêm, re-run `compare-sample WEEK=0` xác nhận lật ✅ (xem bước Verify bên dưới). |
| 5. failure-log | ✅ | 8 entry gắn `**Tuần:** T0` (F-001…F-014, mới thêm ở Phase 4: F-012/13/14) — đạt ngưỡng ≥3. |
| 6. reproducibility | ✅ | `context.dataset_revision` khớp pin `12d76d4d…`; report `artifacts/eval/eval_test_t0-smoke_20260731T134929+0000.json` có đủ provenance; tái lập bằng `PROVIDER=fake make smoke`. |
| 7. git | ✅ (người xác nhận) | Tool đếm 🟡 (11 commit nhắc T0/week0, heuristic substring). Người xác nhận: T0 ship theo 4 phase commit (`f4bd597`→`0c84860`) với report + failure_log + plan §1b cùng landing ở `f3b5edc` (docs(t0): week0 report + plan §1b số thật, đóng dấu T0 DONE) và `a5ef65b` (failure-log F-012/13/14) — đúng nghi thức "report+failure_log+plan-status cùng landing". |

### Metric (chỉ khi cùng cấu hình)

➖ Không so được ở T0 theo thiết kế: số hiện tại là tripwire fake-embedder / slice 500-doc / 573 câu
(không phải benchmark 788-câu full-corpus 61.425 doc mà `sample-baselines.yaml` yêu cầu để so
head-to-head). Same-config guard trong `compare_sample.py` từ chối in bảng số vì lẫn hai thứ không
so được là vô nghĩa, không phải vì công cụ lỗi. Real head-to-head đầu tiên (BM25 + underthesea,
full corpus, split test) dự kiến ở T2.

**Bar (quyết định 3):** có số thật + giải thích per-query = ĐẠT. Vượt mẫu là bonus. T0 là tuần
skeleton/cấu trúc (trục 3 = ➖ theo `docs/comparison-framework.md` bảng "Trục 3 bật ở tuần nào"),
nên không áp dụng bar này tuần này.

**Kết luận (một câu):** ở T0, dự án này on-track so với mẫu trên cấu trúc/quy trình (structure,
tests, failure-log, reproducibility, git đều ✅ sau xác nhận tay); mẫu rộng hơn vì đã ở T2+
(bm25/splade/tokenize/dashboard) — điều này kỳ vọng vì mẫu đi trước, không phải dự án này tụt hậu.

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
