# Tiến độ lộ trình — T0 đã làm & kế hoạch T1–T8

> Tổng hợp tiến độ dự án theo lộ trình 8 tuần trong `docs/plan.md`. Xem cách so sánh với
> dự án mẫu ở `docs/comparison-framework.md`.

## 1. Đã hoàn thành — T0

T0 dựng theo `docs/t0.md` (19 bước), chia **4 phase**; mỗi phase verify → report → commit. Sau đó
thêm **bộ so sánh vs dự án mẫu**.

| Phase | t0.md | Đã làm | Commit |
|---|---|---|---|
| **1** | 1–6 | Scaffold repo · `pyproject`+uv · `docker-compose` (Qdrant) · `config/settings.py` (base_dir field, collection derive, fake tách slug) · `schemas.py` · `providers/` (base/fake/gemini/registry) | `f4bd597`, `77091e3` |
| **2** | 7–13 | loader+`verify-dataset` (revision pin `12d76d4d`) · clean/metadata/chunk · golden (leakage guard 24, dedupe 102) · pipeline gold-covering · qdrant_store (named vector, UUID5) · vector retriever · metrics/harness | `58a870b`, `85c845e`, `e2aa93c`, `282de02` |
| **3** | 14–16 | `cli.py` (Typer 8 lệnh) · Makefile targets · test suite + integration offline smoke (in-memory Qdrant) | `f24efd2`, `c3f7176` |
| **4** | 17–19 | `PROVIDER=fake make smoke` (573/788 câu, Recall@10 0.9555 tripwire) · `failure_log.md` ≥3 case · `reports/week0.md` · `plan §1b` số thật + `§3` T0 ✅ DONE | `a5ef65b`, `f3b5edc`, `0c84860` |
| **+So sánh** | — | Framework 7 trục + `sample-baselines.yaml` + `make compare-sample` + guide self-serve · ghi kết quả so sánh T0 vào `reports/week0.md` | `29c7616`, `67ddd1c`, `ea97bef`, `6d364bf` |

**Xác nhận chất lượng:** 115 test pass, `make lint` sạch, mọi số tái lập được, không bịa số.

**4 giả định dữ liệu đã verify (`plan §1b`):** corpus 61.425 chunk sẵn mức Điều · nhãn/câu ~1.0
(single-label) · leakage 24 · trùng `_id` 102.

## 2. Kế hoạch T1–T8

### Vòng lặp chuẩn mỗi tuần (theo `plan §8`)
1. **Đầu tuần:** viết 1 câu hỏi "tuần này chứng minh/bác bỏ điều gì?".
2. **Thêm 1 signal/tầng mới** (code trong `src/`, thêm dep nếu cần) — đúng cột "Làm gì" của `plan §3`.
3. **Giữa tuần:** cố tình chạm failure → log ≥3 vào `failure_log.md` (gắn `**Tuần:** TN`).
4. **Benchmark full-corpus:** `make ingest LIMIT=0 && make index && make eval RETRIEVER=<...> LABEL=tN-...` (luôn `--split test`).
5. **Regression per-query:** `make compare` (2 run gần nhất) — hỏi "bao nhiêu câu tệ đi?" trước khi nhận lift.
6. **Viết `reports/weekN.md`** theo §8 (số + lift + ≥3 failure + "tại sao").
7. **So với mẫu:** `make compare-sample WEEK=N CS_ARGS="--emit-md"` → dán block vào report; refresh `sample-baselines.yaml` + bump `meta.sample_commit` nếu mẫu đã công bố tuần đó.
8. **Chốt:** `make test` + `make lint` xanh → cập nhật `plan §3` (TN ✅ + link) → commit.

### Trọng tâm từng tuần (từ `plan §3/§4` + `comparison-framework.md`)

| Tuần | Deliverable | Signal mới | Module mới | Trục-3 (metric) so mẫu |
|---|---|---|---|---|
| **T1** | #5 Eval Harness | DeepEval + LLM-as-judge (rubric relevance+faithfulness, calibrate ~30 mẫu người), regression gate; port `compare.py` | `src/eval/compare.py` | ➖ (chưa retriever mới) → so scope; LLM-judge = bonus vượt mẫu |
| **T2** | #6 Dashboard (bản đầu) | BM25: tokenize VN (pyvi/underthesea), tuning k1/b, `sweep` | `retrieve/bm25.py`, `ingest/tokenize.py` | ✅ head-to-head (số thật đầu tiên; mẫu R@10 0.8610) |
| **T3** | #1 Ingestion | Vector/dense thật (Gemini), thử dimension, đo vs BM25; đo F-001 (Điều dài bị cắt) → chính sách truncation | (vector đã có) | own-bar (mẫu chưa có) |
| **T4** | #2 Hybrid, #4 Rerank | RRF fusion (sparse+dense) + Gemini reranker; đo RAM/latency thật | `retrieve/hybrid.py`, `rank/` | own-bar + latency/RAM |
| **T5** | #3 Metadata Filter | Metadata làm retriever thứ 3 (loại VB/năm/hiệu lực/quyền); query rewrite/route; F-011 load-bearing | `retrieve/metadata.py` | own-bar, partial (precision↔recall) |
| **T6** | — | Neo4j (dẫn chiếu chéo, multi-hop) + filesystem search | `graph/` | metric trên subset multi-hop |
| **T7** | — | OCR PDF luật scan (tập bổ sung nhỏ) → cross-modal, cùng index | `parse/` | ➖ vs mẫu (OCR set riêng, không phải 788) |
| **T8** | #6 Dashboard, #7 Report | Chatbot + citation grounded; Dashboard hoàn chỉnh; Production Report (latency/RAM/cost/quality/failure) | `generate/`, `dashboard/` | full scorecard mọi retriever |

### Bất biến giữ suốt mọi tuần
`test` là split benchmark · đổi embedding = re-index toàn bộ · không leakage · không so 2 tập câu
khác nhau · baseline BM25/underthesea là con số duy nhất để so (mọi retriever mới phải bám vào đó).
