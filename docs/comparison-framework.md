# Khung so sánh hàng tuần: dự án này vs dự án mẫu (T0→T8)

> Mục tiêu: cuối mỗi tuần đánh giá **đo được, lặp lại được** xem dự án hiện tại có "bám kịp /
> ngang chuẩn tham chiếu" (`../aie-rag-sample-project/`) hay không — cả **số benchmark** lẫn
> **chất lượng kỹ thuật/quy trình**. Nền so sánh: cùng dataset + cùng revision pin
> `12d76d4d…` + cùng toolchain + cùng `test` split 788 câu + cùng invariant + cùng
> `EvalReport`/harness.

## Ba tạo tác

1. **File này** (`docs/comparison-framework.md`) — rubric 7 trục × 8 tuần + template mục report.
2. **`docs/sample-baselines.yaml`** — nguồn số của mẫu (curate tay; mẫu artifacts gitignored →
   chỉ report/README của mẫu là số chuẩn). Mỗi entry ghi rõ nguồn + config + commit mẫu.
3. **`make compare-sample WEEK=N`** (`src/eval/compare_sample.py`) — so cấu trúc tự động +
   guard cùng-cấu-hình + scorecard 7 trục; xuất bảng rich + JSON + (tuỳ chọn) block markdown.

## 3 nguyên tắc (theo quyết định đã chốt)

- **Holistic:** chấm cả metrics (nơi so được) lẫn kỹ thuật/quy trình.
- **Chuẩn đạt (T2+):** có **số thật tái lập được + giải thích per-query** = ĐẠT. Vượt số mẫu là
  **bonus, không phải cửa**. Tool **luôn exit 0** — bảng điểm tham chiếu, không phải build gate.
- **Không bao giờ bịa số.** Tuần nào mẫu chưa có số full-corpus/788-test → `metric_comparable: false`.
- **Own-bar (quyết định 3):** khi mẫu `metric_comparable: false` nhưng dự án này có số thật
  full-corpus 788-test trên đúng revision pin + giải thích per-query, trục 3 = ✅ **own-bar (đạt,
  mẫu chưa có)** — không đợi mẫu công bố mới được tính là đạt.

## 7 trục (áp dụng mọi tuần)

| # | Trục | Cách chấm | Tự đo? |
|---|------|-----------|:------:|
| 1 | Cấu trúc / scope | Module/CLI/retriever mục tiêu của tuần tồn tại & wired, vs bộ module mẫu | ✅ filesystem |
| 2 | Test coverage | `make test` xanh; code mới có test; số test tăng; guard test cho invariant mới | 🟡 đếm (green cần chạy `make test`) |
| 3 | Metrics / rigor | Tuần-metric: có số thật full-corpus 788-test + giải thích per-query. Tuần-cấu-trúc: ➖ | ✅ guard |
| 4 | Docs | `reports/weekN.md` đủ nghi thức §8 + có mục "So với dự án mẫu"; plan/README cập nhật | ✅ presence |
| 5 | Failure-log | ≥3 entry `F-` gắn tuần này, đủ hiện tượng/vì sao/trạng thái | ✅ đếm |
| 6 | Reproducibility | 1 lệnh `make` tái lập số; `context` đủ provenance; revision pin không đổi | ✅ context |
| 7 | Git cadence | Commit/tag tuần; report+failure_log+plan-status cùng landing; số có provenance | 🟡 heuristic |

**Trạng thái:** ✅ on-track · 🟡 partial/cần xác nhận tay · 🔴 behind · ➖ N/A tuần này.

## Trục 3 (metric) bật ở tuần nào

| Tuần | Deliverable | Trục 3 | Baseline mẫu |
|------|-------------|--------|--------------|
| T0 | Skeleton + smoke | ➖ (fake/slice tripwire) | — |
| T1 | #5 Eval Harness | ➖ (không có retriever number mới) | mẫu 🟡 → so *scope* |
| **T2** | #6 Dashboard (BM25) | ✅ **so metric** (số thật đầu tiên) | **có**: BM25/underthesea Recall@10 0.8610 · MRR@10 0.5785 |
| T3 | #1 Ingestion (vector) | so nếu mẫu công bố; nếu không → own-bar | mẫu ⬜ → own-bar |
| T4 | #2 Hybrid, #4 Rerank | so nếu công bố; +latency/RAM thật | mẫu ⬜ → own-bar |
| T5 | #3 Metadata filter | partial (precision↔recall, freshness/permission) | mẫu ⬜ → own-bar |
| T6 | KG / filesystem | metric trên subset multi-hop | mẫu ⬜ |
| T7 | Doc parsing / multimodal | metric trên OCR set nhỏ (KHÔNG phải 788) | ➖ vs mẫu |
| T8 | #6 Dashboard, #7 Report | full scorecard mọi retriever | tuỳ tiến độ mẫu |

*Ghi chú:* T1 = matching per-query + `compare.py` là ✅; thêm DeepEval LLM-judge = bonus (vượt
mẫu). T3 = F-001 (Điều dài bị cắt khi bật Gemini) phải đo. T5 = F-011 (173 record parse fail)
thành load-bearing khi filter theo năm.

### Tiêu chí từng tuần (T1–T8)

Mỗi tuần có cùng 4 trường (đồng đều, không lệch): **Deliverable · Trục-3 mode · Module mới kỳ
vọng + retriever anchor · Failure themes kỳ vọng.**

**T1 — #5 Eval Harness**
- Deliverable: eval harness + per-query compare.
- Trục-3 mode: ➖ (không có retriever number mới) → so *scope*, không so metric.
- Module mới kỳ vọng: `src/eval/compare.py` · retriever anchor: `vector`.
- Failure themes: golden leakage, metric edge case (0 kết quả, câu hỏi lỗi).

**T2 — #6 Dashboard (BM25)**
- Deliverable: BM25 dashboard, tokenize tiếng Việt.
- Trục-3 mode: **metric head-to-head** (số thật đầu tiên) — canonical
  bm25-underthesea Recall@10 0.8610 / MRR@10 0.5785.
- Module mới kỳ vọng: `src/retrieve/bm25.py`, `src/ingest/tokenize.py` · retriever anchor: `bm25`.
- Failure themes: VN tokenize (pyvi vs underthesea).

**T3 — #1 Ingestion**
- Deliverable: ingestion/chunk polish (mẫu chưa công bố số cho tuần này).
- Trục-3 mode: own-bar — **trục 1 tầm thường ✅ (vector retriever có từ T0)**; trọng tâm dồn vào
  trục 3/6 (số thật full-corpus + reproducibility).
- Module mới kỳ vọng: không có module mới · retriever anchor: `vector`.
- Failure themes: F-001 (Điều dài bị cắt khi bật Gemini) phải đo được.

**T4 — #2 Hybrid + #4 Rerank**
- Deliverable: hybrid retrieval + reranker.
- Trục-3 mode: own-bar + latency/RAM thật (số thật của chính dự án, không chờ mẫu).
- Module mới kỳ vọng: `src/rank`, `src/retrieve/hybrid.py` · retriever anchor: `hybrid`.
- Failure themes: fusion churn (câu tốt lên/tệ đi khi trộn), chi phí/độ trễ reranker.

**T5 — #3 Metadata Filter**
- Deliverable: filter theo metadata (năm, loại văn bản, ...).
- Trục-3 mode: own-bar, partial — đánh đổi precision↔recall, freshness/permission.
- Module mới kỳ vọng: `src/retrieve/metadata.py` · retriever anchor: `hybrid`.
- Failure themes: F-011 (173 record parse fail) trở thành load-bearing khi filter theo năm.

**T6 — Knowledge Graph / filesystem**
- Deliverable: truy vấn multi-hop qua KG/filesystem.
- Trục-3 mode: metric trên subset multi-hop (không phải 788 câu full).
- Module mới kỳ vọng: `src/graph` · retriever anchor: `vector`.
- Failure themes: multi-hop dẫn chiếu chéo (Điều này dẫn Điều khác).

**T7 — Document parsing / multimodal**
- Deliverable: parse tài liệu scan/ảnh (OCR).
- Trục-3 mode: **metric trên OCR set nhỏ — KHÔNG phải 788 câu chuẩn**; ➖ vs mẫu (không so được,
  set khác nhau).
- Module mới kỳ vọng: `src/parse` · retriever anchor: `vector`.
- Failure themes: chất lượng OCR (lẫn ký tự, mất cấu trúc Điều/Khoản).

**T8 — Dashboard + Production Report**
- Deliverable: dashboard tổng hợp + Production Report cuối kỳ.
- Trục-3 mode: full scorecard trên mọi retriever đã build.
- Module mới kỳ vọng: `dashboard` · retriever anchor: `hybrid`.
- Failure themes: end-to-end citation grounding (trích dẫn có đúng nguồn không).

## Same-config guard (chỉ hiện bảng metric khi TẤT CẢ đúng, else ➖ + lý do)

1. `report.split == "test"`
2. `context.dataset_revision == pin` (`12d76d4d…`)
3. `report.n_queries == 788`
4. `context.n_documents == 61425` (loại slice như tripwire T0: 573 câu / 500 doc)
5. `sample-baselines[TN].metric_comparable == true`
6. retriever khớp tuần

Phía mẫu chỉ có số aggregate (không có per-query JSON) → **không** bịa churn per-query vs mẫu.
Churn per-query chỉ so trong nội bộ dự án qua `src/eval/compare.py` (`make compare` khi có ở T2).

## Chạy & tự kiểm tra (self-serve)

### Điều kiện trước khi so metric

Để có hàng metric thật (trục 3 = ✅), TRƯỚC hết phải có report full-corpus split=test cho
retriever của tuần: `make ingest LIMIT=0 && make index` rồi
`make eval RETRIEVER=<bm25|vector|hybrid> LABEL=<tN-baseline>`. `compare-sample` tự lấy report
`eval_test_*` mới nhất khớp retriever của tuần (xem `WEEK_RETRIEVER`), hoặc truyền
`--report PATH` để chỉ đích danh. Không có report như vậy → trục 3 hiện
`➖ chưa có run test hiện tại` — đúng dự kiến, **không phải lỗi**.

### Chạy

```bash
make compare-sample WEEK=2                          # in scorecard + guard + ghi JSON
make compare-sample WEEK=2 CS_ARGS="--emit-md"      # + block markdown dán vào report
make compare-sample WEEK=2 CS_ARGS="--validate-sample"  # cảnh báo nếu HEAD mẫu ≠ sample_commit YAML
```

`WEEK=` và `CS_ARGS=` là biến của target Makefile `compare-sample` (không phải flag của
`src/cli.py`); `CS_ARGS` được nối thẳng vào lệnh `uv run python -m src.cli compare-sample`.
Flags passthrough qua `CS_ARGS`: `--retriever`, `--report PATH`, `--current-root PATH`,
`--sample-root PATH`, `--json PATH`, `--emit-md`, `--validate-sample`. Kết quả JSON luôn được
ghi (mặc định `artifacts/compare_sample/compare_sample_week{N}.json`, gitignored).

**Quy tắc thời điểm:** chạy `compare-sample WEEK=N` vào **CUỐI tuần N**, sau khi đã viết
`reports/weekN.md` và log ≥3 failure. Chạy cho một tuần chưa làm sẽ ra `overall: behind` — không
phải vì tool phát hiện vấn đề kỹ thuật, mà đơn giản vì `reports/weekN.md` và ≥3 failure entry gắn
tuần đó chưa tồn tại. Đó là "tuần chưa làm", không phải tụt hậu; đừng hoảng khi thấy `behind` cho
một tuần trong tương lai.

### Đọc scorecard — 4 ký hiệu

| Ký hiệu | Ý nghĩa |
|:---:|---------|
| ✅ | Đạt / ngang chuẩn — tool tự đo được, không cần xác nhận thêm. |
| 🟡 | Một phần / **cần người xác nhận tay** — tool chỉ đếm hoặc dùng heuristic. |
| 🔴 | Behind — thiếu deliverable bắt buộc của trục (ví dụ thiếu `reports/weekN.md`). |
| ➖ | N/A tuần này — trục không áp dụng hoặc chưa có dữ liệu để chấm, không phải lỗi. |

### 7 trục nghĩa là gì + trục nào tool tự chấm vs người phải tự phán

- **1. structure** — module/CLI/retriever mục tiêu của tuần có tồn tại trên filesystem không.
  Tool tự chấm được (✅/🟡 dựa trên phép so sánh đường dẫn).
- **2. tests** — tool chỉ **ĐẾM** số file `test_*.py` và số hàm `def test_`, không chạy chúng →
  **luôn 🟡**; người phải tự chạy `make test` để biết có xanh hay không.
- **3. metrics** — guard cùng-cấu-hình (xem bên dưới) tự chấm được: ✅ khi so head-to-head được
  hoặc own-bar đạt, ➖ khi chưa có run/chưa so được. Tool tự chấm.
- **4. docs** — tool chỉ kiểm tra **sự tồn tại** của `reports/weekN.md` và chuỗi con "So với dự
  án mẫu" trong đó → chỉ biết "có mặt", không biết "có đạt nghi thức §8 không" (câu hỏi đầu tuần,
  ≥3 failure giữa tuần, số liệu + lift cuối tuần); **người phải tự phán** report có đủ chất lượng
  nghi thức không.
- **5. failure-log** — đếm entry `F-` gắn `**Tuần:** TN`, yêu cầu ≥3. Tool tự chấm.
- **6. reproducibility** — kiểm `context.dataset_revision` của report có khớp pin không, và có
  report hay không. Tool tự chấm.
- **7. git** — chỉ **đếm** commit message có nhắc `tN`/`weekN` (case-insensitive substring) →
  **luôn 🟡**; đây là heuristic, không xác minh nội dung commit. Người phải tự xác nhận
  `reports/weekN.md`, `failure_log.md`, và trạng thái tuần trong `plan.md` cùng landing (cùng
  commit hoặc cùng đợt commit cuối tuần).

**Ghi chú:** `overall` (on-track/review/behind) chỉ suy ra từ 3 trục "cứng" — 1 (structure), 3
(metrics), 5 (failure-log). Trục 2/4/7 luôn hiển thị nhưng không quyết định `overall` vì bản chất
chúng cần người xác nhận tay.

### Same-config guard — cái gì bị từ chối & vì sao

Trục 3 chỉ hiện bảng metric head-to-head khi **cả 6 điều kiện** dưới đây đúng, ngược lại trả về
➖ kèm lý do cụ thể (không im lặng):

1. `report.split == "test"` — không so trên `dev` (đó là split để dành fine-tune).
2. `context.dataset_revision == pin` (`12d76d4d…`) — không so hai revision dataset khác nhau.
3. `report.n_queries == 788` — loại slice câu hỏi (ví dụ tripwire T0 dùng 573 câu).
4. `context.n_documents == 61425` — loại slice tài liệu (ví dụ tripwire T0 dùng 500 doc).
5. `sample-baselines.yaml[TN].metric_comparable == true` — mẫu phải có số full-corpus/788-test
   đã công bố cho tuần đó.
6. Retriever khớp `WEEK_RETRIEVER[TN]` — không so BM25 hiện tại với vector của mẫu.

Lý do: trừ metric của một slice 500-doc/573-câu cho baseline chạy trên 788/61.425 ra một con số
**vô nghĩa** (không phải "tệ hơn" hay "tốt hơn" — không so được), nên tool chủ động từ chối thay
vì hiện một con số gây hiểu lầm. Cùng triết lý với guard nội bộ `src/eval/compare.py` (không so
hai tập câu khác nhau, không bịa churn per-query giữa hai nguồn không tương thích).

### Tự kiểm tra độc lập (double-check)

1. **Chạy lại cùng lệnh** — structural snapshot + same-config guard đều tất định (không random);
   chạy `make compare-sample WEEK=N` hai lần liên tiếp phải ra scorecard giống hệt nhau (trừ khi
   có report/commit mới xen giữa).
2. **Mở JSON** `artifacts/compare_sample/compare_sample_week{N}.json` — xem trực tiếp
   `axes[...].status`/`evidence`, `metric.reasons`, `report_run_id` để đối chiếu với bảng rich in
   ra console.
3. **Đối chiếu số mẫu** — mở `../aie-rag-sample-project/reports/week2.md` và
   `../aie-rag-sample-project/README.md`, so với `metrics:` trong `docs/sample-baselines.yaml`
   xem có chép đúng không; chạy `CS_ARGS="--validate-sample"` để tool tự cảnh báo nếu HEAD hiện
   tại của mẫu đã vượt qua `meta.sample_commit` (nghĩa là mẫu có thể đã công bố số mới hơn số
   đang chép trong YAML).
4. **Tái lập số hiện tại** — chạy lại `make eval RETRIEVER=<...> ` full corpus split=test, kiểm
   tra số ra khớp với report mà `compare-sample` đã chọn (`report_run_id`/`report_label` trong
   JSON).

### Ví dụ đọc một scorecard

Trạng thái **thật** của dự án này tại T0 hôm nay (không phải ví dụ giả định):

> `make compare-sample WEEK=0` → overall: on-track.
> - `1. structure ✅` 25 src vs mẫu 29; không thiếu module tuần; mẫu có thêm bm25/splade/tokenize/
>   rank/generate/dashboard/notebooks (mẫu đã tới T2+, bình thường).
> - `2. tests 🟡` 12 files/115 funcs (mẫu 15/179). 🟡 vì tool chỉ đếm — **bạn chạy `make test`**
>   để biết có xanh.
> - `3. metrics ➖` số T0 là tripwire fake-embedder slice 500-doc, guard từ chối so. Đúng thiết kế.
> - `4. docs 🟡` có `reports/week0.md` nhưng thiếu mục "So với dự án mẫu" (T0 làm trước khung).
>   Từ T1 dán block `--emit-md` là ✅.
> - `5. failure-log ✅` 8 entry gắn T0 (≥3).
> - `6. reproducibility ✅` report có provenance, revision khớp pin.
> - `7. git 🟡` 10 commit nhắc T0/week0; 🟡 vì heuristic — bạn tự xác nhận cùng landing.
>
> Kết luận: 🟡 ở trục 2/4/7 là "người tự phán", không phải điểm trừ của tool; on-track vì 1/3/5
> đều ✅/➖.

Tương phản: `make compare-sample WEEK=1` chạy hôm nay (T0 chưa xong T1) → `behind`, chỉ vì
`reports/week1.md` và ≥3 failure entry gắn T1 chưa tồn tại — đây là "tuần chưa làm", không phải
tụt hậu kỹ thuật.

## Bảo trì `sample-baselines.yaml` (nghi thức hàng tuần)

Khi mẫu công bố tuần mới: chép số từ report đã commit của mẫu vào YAML, bump `meta.sample_commit`
(= `git -C ../aie-rag-sample-project rev-parse HEAD`), rồi chạy `--validate-sample` để chắc số
chưa lệch. **Không** chạy `make eval` của mẫu để lấy số (nặng: corpus 110MB, underthesea ~397s,
T3+ cần API key + tốn tiền).

## Template mục report — dán vào cuối mỗi `reports/weekN.md` (trước Exit criteria)

`make compare-sample WEEK=N CS_ARGS="--emit-md"` sinh sẵn block dưới đây, đã điền:

```markdown
## So với dự án mẫu (T{N})

> Nguồn số dự án mẫu: `docs/sample-baselines.yaml`. Hàng metric chỉ xuất hiện khi cùng cấu hình
> (revision + split=test + full corpus + 788 câu); nếu không, đánh ➖ kèm lý do. Không bịa số.

### Scorecard 7 trục
| Trục | Trạng thái | Bằng chứng |
|------|:----------:|------------|
| 1. structure | … | … |
| … | … | … |

### Metric (chỉ khi cùng cấu hình)
| metric | current | sample | Δ |
|--------|--------:|-------:|--:|
| recall@10 | … | 0.8610 | … |

**Bar (quyết định 3):** có số thật + giải thích per-query = ĐẠT. Vượt mẫu là bonus.
```
