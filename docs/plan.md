# PLAN — RAG Tra cứu Luật Việt Nam

> **Mục tiêu:** Xây một hệ thống Retrieval có thể **Đo – Gỡ lỗi – Cải thiện**.        
> **Sản phẩm cuối:** Chatbot hỏi–đáp văn bản luật VN, có benchmark + trace + báo cáo production.        
> **Triết lý:** Dựng hệ thống chạy ngay ngày đầu → chạm lỗi sớm → *Thử nghiệm – Đo – Hỏi tại sao*.        

---

## 1. Quyết định chính

| Quyết định | Lý do |
|-----------|-------|
| Nhịp độ **1 buổi/tuần × 8 tuần** | Bám syllabus, có thời gian đào sâu + viết report. |
| Provider mặc định **Gemini** (embedding + generation + judge), nhưng **đặt sau lớp abstraction** — đổi provider = đổi config | 1 API key, chi phí thấp, không khoá cứng vendor. |
| **Qdrant** chạy local qua Docker | Miễn phí, đo RAM/latency thật cho Production Report. |
| Làm đủ **7 deliverables**, mỗi cái "đủ tốt để demo + đo được" | Không nghiêng hẳn về một hướng. |

**Dataset:** `GreenNode/zalo-ai-legal-text-retrieval-vn` — có sẵn corpus luật + golden labels (câu hỏi → điều luật liên quan). Sẽ verify schema thật ở Tuần 0 (`make verify`) — kết quả và giả định cần sửa (nếu có) sẽ ghi ở §1b.

**Lớp abstraction (dựng ngay Tuần 0):**
```
EmbeddingProvider.embed(texts, task_type) -> vectors
LLMProvider.complete(prompt) / .judge(rubric, sample)
```
⚠️ Đổi embedding = **re-index toàn bộ** (khác dimension) → mỗi bộ model gắn 1 collection riêng. Generation/judge/reranker đổi tự do. Judge nên khác provider với generation để giảm bias.

---

## 1b. Xác nhận dữ liệu thật (T0)

Chạy `make verify` (`GreenNode/zalo-ai-legal-text-retrieval-vn` @ revision
`12d76d4d04b94ceada970fcfbe7fec20bfa97389`) — toàn bộ 8 check khớp expected=observed:
corpus 61.425 record, queries 3.298 dòng / 3.196 `_id` duy nhất, qrels train 2.505 nhãn /
2.432 câu, qrels test 793 nhãn / 788 câu, overlap train∩test 24 câu. 4 giả định ở §1:

1. **Corpus đã chunk sẵn ở mức Điều?** → **Có.** Mẫu `01/2009/tt-bnn+1..5` mỗi record đúng
   một Điều — xác nhận `chunk_strategy=article` mặc định là hợp lý (giữ nguyên đơn vị record).
2. **Trung bình nhãn/câu?** → hầu như single-label, không cần metric graded phức tạp cho T0-T1.
   Test: mean **1.006**, chỉ **5/788** multi-label (0,6%). Train: mean **1.03**, **66/2.432**
   multi-label (2,7%).
3. **Leakage train↔test?** → **24** query id xuất hiện ở cả `qrels/train.jsonl` và
   `qrels/test.jsonl`. Đã loại khỏi **dev** (còn 2.408 câu), giữ nguyên trong **test** (788
   câu) — xem `failure_log.md` F-002.
4. **Dòng trùng `_id` trong `queries.jsonl`?** → **102** dòng trùng trên tổng 3.298 dòng
   (3.196 `_id` duy nhất) — dedupe giữ dòng đầu tiên. Xem F-003.

Không có giả định nào ở §1 cần sửa — cả 4 điều đúng như kỳ vọng ban đầu.

---

## 2. Kiến trúc (pipeline end-to-end)

```
                  ┌──────────────────────────────────────────────────┐
                  │            EVALUATION HARNESS (T1)               │
                  │   Recall@k · MRR · nDCG · LLM-as-judge           │
                  │   (chạy regression sau MỖI thay đổi)             │
                  └────▲───────────▲───────────▲─────────────▲───────┘
                       │ đo        │ đo        │ đo          │ đo
   ┌──────────┐   ┌────┴─────┐  ┌──┴───────┐  ┌┴─────────┐  ┌┴──────────┐
   │ INGEST   │   │  INDEX   │  │ RETRIEVE │  │  RANK    │  │ GENERATE  │
   │ load     │──▶│ dense    │─▶│ BM25     │─▶│ RRF      │─▶│ trả lời   │
   │ clean    │   │ sparse   │  │ + vector │  │ fusion   │  │ + citation│
   │ chunk    │   │ metadata │  │ + filter │  │ + rerank │  │ (grounded)│
   │ metadata │   │ (Qdrant) │  │          │  │ (Gemini) │  │           │
   └────┬─────┘   └──────────┘  └──────────┘  └──────────┘  └─────┬─────┘
        │                                                         │
        └──────────── TRACE / OBSERVABILITY (log mọi bước) ───────┘
                      → hiển thị trên Retrieval Dashboard (T8)
```

**Nguyên tắc:** mỗi tuần thêm **một signal/tầng mới** → đo lift so với tuần trước → hỏi *tại sao* → ghi vào `failure_log.md`.

**Thách thức dataset & đối sách:**
- Điều luật dài → **chunk theo cấu trúc**: Điều → Khoản → Điểm. 
- Tiếng Việt → **word segmentation** (pyvi/underthesea) cho BM25. 
- Dẫn chiếu chéo → lưu references vào metadata (nền cho Knowledge Graph).
- Nhiều điều đúng/câu → metric dùng Recall@k, MAP, nDCG (không chỉ hit@1). 

---

## 3. Lộ trình 8 tuần

> **Thứ tự:** khung + eval trước → từng signal retrieval một → lớp agentic → ráp + báo cáo.        
> **Luật vàng:** cuối mỗi tuần phải có **số benchmark mới** + **≥3 failure case**.

| Tuần | Syllabus | Làm gì | Deliverable | Status |
|------|-----------------|--------|-------------|--------|
| **T0** | **01 — Tổng quan** | Skeleton repo, Docker Qdrant, lớp abstraction, index 500 docs → vector search thô | Smoke test | ✅ [week0](../reports/week0.md) |
| **T1** | **02** — Evaluating Search Systems | Golden set, split dev/test, metrics (Recall/MRR/MAP/nDCG), DeepEval + LLM-as-judge | **#5** Eval Harness | ⬜ TODO |
| **T2** | **03** — Lexical Search (BM25) | VN tokenize, BM25 tuning (k1/b/length norm), đo vs baseline | **#6** Dashboard (bản đầu) | ⬜ TODO |
| **T3** | **04** — Semantic Search (Vector) | Ingestion chuẩn (clean→chunk→embed→upsert), thử dimension, đo vs BM25 | **#1** Ingestion | ⬜ TODO |
| **T4** | **05** — Hybrid + Reranking | RRF fusion (sparse+dense) + Gemini reranker, đo RAM/latency thật | **#2** Hybrid, **#4** Rerank | ⬜ TODO |
| **T5** | **06** — Query Understanding + Orchestration | Metadata làm retriever thứ 3 (loại VB, năm, hiệu lực, quyền), query rewrite/decomposition/routing | **#3** Metadata Filter | ⬜ TODO |
| **T6** | **07** — Knowledge Graph + Filesystem | Neo4j cho dẫn chiếu chéo, multi-hop, filesystem search (grep/cat/ls/find) | — | ⬜ TODO |
| **T7** | **08** — Document Parsing + Multimodal | OCR PDF luật scan (tập bổ sung nhỏ) → cross-modal, cùng index | — | ⬜ TODO |
| **T8** | *(Final Project)* | Chatbot + citation, Dashboard, Production Report | **#6** Dashboard, **#7** Report | ⬜ TODO |

Mỗi tuần theo cấu trúc: 🎯 Mục tiêu · 🔬 Fail-fast · 📐 Measure · ❓ Ask why · 📦 Deliverable · ✅ Exit.

**Status legend:** ⬜ TODO · 🟡 IN PROGRESS · ✅ DONE — khi DONE thay bằng `✅ [repo](https://github.com/...)` trỏ tới GitHub thực hành của tuần đó.

---

## 4. Bảy Deliverables

| # | Deliverable | Hoàn thiện | Đo bằng |
|---|-------------|-----------|---------|
| 1 | Ingestion Pipeline | T3 | tái lập 1 lệnh, thời gian + cost ingest |
| 2 | Hybrid Search | T4 | Recall/nDCG lift vs single retriever |
| 3 | Metadata Filtering | T5 | precision↔recall, demo freshness/permission |
| 4 | Reranking | T4 | quality lift vs latency cost |
| 5 | Evaluation Harness | T1→T8 | 1 lệnh ra full metric report |
| 6 | Retrieval Dashboard | ~~T8~~ **bản đầu ở T2** | xem trace + so cấu hình |
| 7 | Production Report | T8 | latency/RAM/cost/quality/failure |

---

## 5. Cấu trúc Repo

```
final-project/
├── pyproject.toml              # uv-managed deps
├── uv.lock
├── Makefile                    # make ingest / eval / dashboard / up / down
├── docker-compose.yml          # Qdrant (+ Neo4j từ T6)
├── .env.example                # GEMINI_API_KEY, QDRANT_URL, COLLECTION_NAME...
├── .gitignore
├── README.md
│
├── config/
│   └── settings.py             # đọc .env → {provider, embed_model, dim, collection}
│
├── data/
│   ├── raw/                    # dataset HF tải về (không commit)
│   ├── processed/              # chunks + metadata đã xử lý
│   └── golden/                 # golden set: test/ (benchmark, mọi tuần) · dev/ (không eval — dành cho embedding fine-tuning sau này)
│
├── src/
│   ├── providers/              # lớp abstraction: EmbeddingProvider, LLMProvider
│   ├── ingest/                 # load · clean · chunk (Điều/Khoản) · metadata
│   ├── index/                  # Qdrant client · dense + sparse upsert
│   ├── retrieve/               # bm25 · vector · hybrid (RRF) · metadata filter
│   ├── rank/                   # fusion · Gemini reranker
│   ├── generate/               # chatbot answer + citation (grounded)
│   ├── graph/                  # Neo4j: entity/relation, multi-hop      (T6)
│   ├── parse/                  # OCR / multimodal ingest                (T7)
│   └── eval/                   # DeepEval harness · metrics · LLM-judge
│
├── dashboard/                  # Retrieval Dashboard (Streamlit/Gradio)  (T8)
├── notebooks/                  # 00_smoke_test.ipynb, khám phá theo tuần
├── tests/                      # unit test cho retriever / provider contract
├── reports/                    # week1.md ... week8.md · FINAL_REPORT.md
├── failure_log.md              # taxonomy failure case (cập nhật mỗi tuần)
└── PLAN.md
```

*Khác biệt thực tế sau T0:* plan nằm ở `docs/plan.md`; `src/graph/` và `src/parse/` sẽ tạo
ở T6/T7; thêm `src/schemas.py` (contract dùng chung giữa các package) và `src/cli.py`
(entrypoint cho mọi target trong Makefile).

---

## 6. Eval Harness — cốt lõi (dựng T1)

- **Contract chung:** mọi retriever cài `retrieve(query, k) → [(doc_id, score)]`.
- **Metrics:** Recall@{1,5,10}, Precision@k, MRR, MAP, nDCG@{5,10}, latency p50/p95, RAM, cost.
- **LLM-as-judge:** rubric relevance + faithfulness, calibrate vs human ~30 mẫu.
- **Regression gate:** mỗi thay đổi chạy `make eval`; metric tụt phải giải thích được.
- **Split:** `test` (từ qrels/test) là benchmark chuẩn cho mọi tuần — không retriever nào ở đây train trên gì cả, nên không có khái niệm "tune trên dev rồi chốt trên test" cần bảo vệ. `dev` (từ qrels/train) không dùng để eval — để dành cho phần sau nếu có tuần fine-tune embedding, khi đó mới cần một tập validation riêng.

---

## 7. Rủi ro chính

| Rủi ro | Giảm thiểu |
|--------|-----------|
| Gemini rate limit / cost | Batch, cache embedding, thử dim nhỏ trước. |
| Chunking sai | Chốt chiến lược chunk theo cấu trúc ở T3, đo ngay. |
| BM25 tiếng Việt kém | So sánh pyvi vs underthesea sớm ở T2. |
| Reranker phụ thuộc vendor | Có Gemini-as-reranker nội bộ dự phòng. |
| Scope phình to | Mỗi deliverable chỉ cần "đủ tốt để đo & demo". |

---

## 8. Nghi thức hàng tuần

1. **Đầu tuần** — viết 1 câu hỏi "tuần này muốn chứng minh/bác bỏ điều gì?".
2. **Giữa tuần** — build, cố tình chạm failure, log lại.
3. **Cuối tuần** — chạy `make eval`, viết `reports/weekN.md` (số liệu + lift + ≥3 failure + "tại sao").
4. Cập nhật `failure_log.md` — nguyên liệu cho Production Report cuối.

---
