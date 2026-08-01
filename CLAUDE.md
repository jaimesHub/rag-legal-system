# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Dự án này là gì

RAG tra cứu văn bản pháp luật Việt Nam, xây theo hướng **đo được – gỡ lỗi được – cải thiện được** (lộ trình 8 tuần T0→T8). Dataset: `GreenNode/zalo-ai-legal-text-retrieval-vn` (format BEIR/MTEB).

**Trạng thái hiện tại: T0 ✅ DONE (xem `reports/week0.md`) — T1 (Eval Harness đầy đủ: DeepEval + LLM-as-judge) chưa bắt đầu.** Skeleton đã dựng đủ theo `docs/plan.md` §5 (`config/`, `src/`, `tests/`, `Makefile`, `pyproject.toml`, `docker-compose.yml`...). Mọi lệnh ở mục "Lệnh" bên dưới **đã chạy được thật** — `PROVIDER=fake` chạy 100% offline (dùng cho T0/T1); các phần cần Gemini thật (vector index chất lượng, LLM-judge) chờ `GEMINI_API_KEY` và các tuần T1/T3 trở đi.

## Tài liệu điều hành (LUÔN follow)

- **`docs/plan.md`** — kế hoạch 8 tuần, quyết định kiến trúc, cấu trúc repo, eval harness. Đây là kim chỉ nam của mọi việc (hub — mọi doc khác trỏ vào đây, không lặp lại nội dung của nó).
- **`docs/weekN/tN.md`** — checklist thực hiện chi tiết cho tuần N, mỗi bước kèm cách verify (mẫu: `docs/week0/t0.md`, 19 bước). Bám sát khi dựng tuần đó; xem quy ước "Nhật ký thực thi" ở mục Quy ước bên dưới.
- **`failure_log.md`** — taxonomy failure case (F-001…), nguyên liệu cho Production Report. Cập nhật mỗi tuần, ghi ≥3 case/tuần.
- **`docs/comparison-framework.md`** — khung 7 trục so sánh tiến độ với dự án mẫu mỗi tuần (`make compare-sample WEEK=N`); nguồn số mẫu ở `docs/sample-baselines.yaml`.
- **`README.md`** — điểm vào cho người đọc: mission, trạng thái, quickstart, trỏ vào `docs/plan.md`/`reports/`/`failure_log.md`. Không lặp lại roadmap hay bảng rủi ro (đã có ở `plan.md`).

Khi trạng thái tài liệu cho các tuần **chưa tới** (ví dụ các dòng ⬜ TODO ở `docs/plan.md` §3 từ T1 trở đi) mâu thuẫn với việc "đã làm xong": đó là **cố ý** — dự án chưa verify dữ liệu/kết quả thật của tuần đó. **Không** tự điền số liệu/kết quả chưa có; chỉ cập nhật `plan.md` §3 (trạng thái tuần) **sau khi** có số thật từ `make eval`. (T0 đã qua giai đoạn này — `plan.md` §1b đã điền số thật từ `make verify`, xem `reports/week0.md`.)

**Giữ file này ≤ 200 dòng.** CLAUDE.md chỉ chứa chỉ dẫn cốt lõi luôn cần trong ngữ cảnh; chi tiết dài thuộc về `docs/`. Trước khi thêm nội dung làm vượt 200 dòng: **dừng, không tự cắt** — đề xuất tách phần phù hợp ra doc riêng (ví dụ tech stack chi tiết → `docs/plan.md`, checklist tuần → `docs/weekN/`) và để lại một dòng trỏ tới, rồi chờ xác nhận.

## SOURCE OF TRUTH — dự án mẫu

Một dự án mẫu đã hoàn thành một phần (T0, T2 xong) đóng vai trò chuẩn tham chiếu cho tech stack, convention, cấu trúc thư mục, và cách giải quyết vấn đề. **Nó cập nhật hàng tuần** — khi cần đối chiếu, đọc bản mới nhất (local hoặc GitHub).

- **Repo mẫu:** `../aie-rag-sample-project/` — https://github.com/ContextBoxAI/aie-rag-sample-project
- **SOURCE OF TRUTH 1:** `../aie-rag-sample-project/README.md` — https://github.com/ContextBoxAI/aie-rag-sample-project/blob/main/README.md
- **SOURCE OF TRUTH 2:** `../aie-rag-sample-project/docs/plan.md` — https://github.com/ContextBoxAI/aie-rag-sample-project/blob/main/docs/plan.md
- **Lessons:** `../aie-rag-sample-project/failure_log.md` — https://github.com/ContextBoxAI/aie-rag-sample-project/blob/main/failure_log.md

Khi cần tech stack / convention / folder structure / rules mà tài liệu của dự án này chưa nói rõ, **tham khảo dự án mẫu** rồi áp dụng cho phù hợp — đừng tự phát minh khác đi. Dự án này là bản build-from-scratch riêng, không phải bản sao; giữ nguyên các quyết định kiến trúc, được tự do khác ở chi tiết triển khai.

## Kiến trúc (đích, theo `docs/plan.md` §2 & §5)

Pipeline một chiều, mỗi lớp chỉ phụ thuộc lớp trước — dựng theo đúng thứ tự này (chi tiết ở `docs/week0/t0.md`):

```
ingest → index → retrieve → rank → generate
                    ↑ mọi lớp đo bằng EVAL HARNESS (regression sau mỗi thay đổi)
```

- `config/settings.py` — nguồn cấu hình **duy nhất**: `.env` → `{provider, embed_model, embed_dim, collection, ...}`. Mọi path derive từ field `base_dir` (không hard-code `Path(__file__)`).
- `src/schemas.py` — contract dùng chung giữa các package (`Passage`, `GoldenExample`, ...).
- `src/providers/` — lớp abstraction `EmbeddingProvider.embed(texts, task_type)` / `LLMProvider.complete|judge`; adapter `gemini` (thật) + `fake` (offline, tất định) + `registry` (config → impl).
- `src/ingest/` — loader (HF pin) · clean · chunk (Điều/Khoản) · metadata · tokenize (T2) · pipeline.
- `src/index/` — Qdrant client, named dense vector, payload index cho filter T5.
- `src/retrieve/` — `base.py` = contract `retrieve(query, k) → [(doc_id, score)]`; vector · bm25 · hybrid · metadata filter (thêm dần theo tuần).
- `src/eval/` — golden (dev/test + leakage guard) · metrics · harness (per-query) · compare.
- `src/cli.py` — entrypoint cho mọi target Makefile.

## Tech stack (theo dự án mẫu)

- **Python ≥3.12,<3.14**, quản lý deps bằng **uv** (`package = false` — import trực tiếp từ root `config/`, `src/`; không build distribution).
- **Qdrant** local qua Docker (port 6333 HTTP/dashboard, 6334 gRPC). Cổng 8000–8002, 3000–3001 bị project contextbox khác chiếm → giữ 6333/6334; T8 dùng 8010 (API) + 8501 (dashboard).
- Provider mặc định **Gemini** (embedding + generation + judge), đặt sau lớp abstraction — đổi provider = đổi config.
- Retrieval libs: `bm25s`, `qdrant-client`, `google-genai`, `huggingface-hub`; VN tokenize `pyvi` + `underthesea` (CRF model trong wheel → offline). Test `pytest`, lint `ruff`.

## Lệnh (đã dựng ở T0, chạy được thật — không phải thiết kế đích nữa)

Toàn bộ đi qua `Makefile` (1-1 với lệnh `src/cli.py`, xem `make help`):

```bash
make up / make down / make logs    # Bật/tắt/xem log Qdrant (Docker)
make sync                          # uv sync
make fetch                         # (tuỳ chọn) tải trước dataset vào data/raw/
make verify                        # Tải dataset ở revision pin, assert schema + counts (đã verify §1b)
make golden                        # Sinh data/golden/dev.jsonl + test.jsonl (test = benchmark split)
make ingest LIMIT=500              # clean → chunk → metadata → data/processed/ (LIMIT=0 = full corpus, T2+)
make index                         # embed + upsert vào Qdrant
make search Q="..."                # tra cứu ad-hoc (retriever=vector — bm25/hybrid từ T2/T4)
make eval RETRIEVER=vector LABEL=...  # metric report trên split=test
make smoke                         # deliverable T0: verify→golden→ingest→index→evaluate, một lệnh
make compare-sample WEEK=N         # scorecard 7 trục so với dự án mẫu (xem docs/comparison-framework.md)
make test / make lint / make fmt   # pytest / ruff check+format / autoformat
```

- **Smoke test offline:** `PROVIDER=fake make smoke` — hash embedder tất định, không cần mạng/API key. Metric nó in ra là **regression tripwire, KHÔNG phải baseline chất lượng** (số thật T0: Recall@10 0,9555 trên slice 573/788 câu — xem `reports/week0.md`), không đưa vào so sánh retriever.
- **Chưa có `make compare`** (per-query 2-run, nội bộ dự án) hay `make tokens`/`make sweep`/dashboard — những lệnh đó thuộc T1/T2, chưa wired vào Makefile dù `src/eval/compare.py` đã tồn tại.
- **Chạy một test:** `uv run pytest tests/unit/test_metrics.py::test_name` (hoặc `-k <pattern>`). Test đánh dấu `live` (gọi API thật, tốn tiền) bị deselect mặc định.
- Dataset **tự tải khi cần** vào `data/raw/` (git-ignored) — không có bước tải tay riêng.

## Bất biến — cưỡng chế bằng code, không bằng quy ước

1. **`test` là split benchmark của mọi tuần; `dev` không dùng để eval** (để dành fine-tune embedding sau). Không retriever nào ở đây train trên gì → không có khái niệm "tune trên dev rồi mở test". `evaluate`/`sweep` mặc định `--split test`.
2. **Đổi embedding = re-index toàn bộ.** Tên collection derive từ `embed_model` + `embed_dim`, nên vector hai model khác nhau **không thể lẫn**. `provider=fake` phải dùng model-slug riêng (`fake-embedding`) — vector giả không nhiễm collection thật (F-006).
3. **Không leakage.** 24 query id giao nhau train↔test bị loại khỏi **dev**, giữ nguyên trong **test** (F-002).
4. **Không so hai tập câu khác nhau.** `compare` giao tập query id và cảnh báo khi lệch; mọi so sánh với baseline chạy trên đủ tập câu test.

## Quy ước

- **Code from-scratch nằm trong `notebooks/` (để học); `src/` dùng thư viện.** Notebook đối chiếu bản from-scratch với thư viện để chứng minh chúng tương đương (canary khi thư viện đổi công thức).
- **Baseline là con số duy nhất để so.** Mọi retriever mới phải đánh bại baseline (BM25 + underthesea, toàn corpus, split test) trên đúng cùng tập câu, nếu không thì không đáng chi phí.
- **Đo per-query, không chỉ aggregate.** Số tổng hợp che mất churn (một nửa câu tốt lên đổi lấy nửa kia tệ đi) — luôn hỏi "bao nhiêu câu tệ đi?" trước khi nhận một mức lift (F-009).
- **Nghi thức hàng tuần:** đầu tuần viết 1 câu hỏi cần chứng minh/bác bỏ → giữa tuần cố tình chạm failure, log lại → cuối tuần `make eval` + viết `reports/weekN.md` (số liệu + lift + ≥3 failure + "tại sao") + cập nhật `failure_log.md`.
- **Nhật ký thực thi theo tuần.** Mỗi tuần TN có checklist riêng ở `docs/weekN/tN.md` (mẫu:
  `docs/week0/t0.md`). Nếu tuần đó được chia phase (nhiều buổi/nhiều commit để xong), file
  checklist đó phải có một mục **"Nhật ký thực thi"** ở cuối — bảng `Phase | Bước | Report |
  Commit` trỏ tới các report phase con (`docs/weekN/phaseK-*.md`) và hash commit thật. **Cập
  nhật ngay sau khi mỗi phase xong** (report phase + commit đã landing) — không dồn lại viết
  hồi tưởng cuối tuần, để tránh lặp lại F-012 (tài liệu "trông như đã đo" nhưng không có
  provenance thật, git log không khớp).
- **Đánh giá tác động trước khi đổi.** Khi sửa tính năng cũ hoặc thêm tính năng mới có ảnh
  hưởng tới phần hiện có (schema/contract, provider, retriever, eval harness, Makefile/CLI,
  config, invariant, hoặc doc là source of truth): **dừng lại và cảnh báo trước — không sửa
  ngay.** Trình bày theo thứ tự: (1) ⚠️ **Warning** — một dòng nêu cái gì bị đụng và vì sao
  đáng lo; (2) **Phân tích** — dây chuyền phụ thuộc bị lay động, có phá `## Bất biến` nào
  không, có bắt re-index / re-eval / cập nhật golden không; (3) **Impact (bảng)** — bảng
  `Thành phần | Ảnh hưởng | Mức độ (🔴 phá vỡ / 🟡 cần chỉnh / 🟢 an toàn) | Việc cần làm`;
  (4) **Đề xuất** — hướng khuyến nghị (nêu rõ 1 lựa chọn ưu tiên) + phương án thay thế nếu có.
  Chỉ code sau khi hướng đi đã rõ. Sửa nhỏ, cục bộ, không lan ra ngoài file đang đụng thì bỏ
  qua nghi thức này.
- `.env` không bao giờ commit; `data/raw/`, `data/processed/` git-ignored; `data/golden/` **được commit** để golden set ổn định qua các tuần.
