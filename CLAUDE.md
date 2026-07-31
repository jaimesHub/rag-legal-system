# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Dự án này là gì

RAG tra cứu văn bản pháp luật Việt Nam, xây theo hướng **đo được – gỡ lỗi được – cải thiện được** (lộ trình 8 tuần T0→T8). Dataset: `GreenNode/zalo-ai-legal-text-retrieval-vn` (format BEIR/MTEB).

**Trạng thái hiện tại: scratch, Brainstorm Phase done — đang chuẩn bị làm T0.** Repo mới chỉ có tài liệu (`docs/`, `failure_log.md`, README stub); **chưa có** code, `Makefile`, `pyproject.toml`, `docker-compose.yml`. Mọi lệnh mô tả bên dưới là **thiết kế đích** kế thừa từ dự án mẫu, sẽ được dựng trong T0 — chưa chạy được cho tới khi skeleton tồn tại.

## Tài liệu điều hành (LUÔN follow)

- **`docs/plan.md`** — kế hoạch 8 tuần, quyết định kiến trúc, cấu trúc repo, eval harness. Đây là kim chỉ nam của mọi việc.
- **`docs/t0.md`** — checklist 19 bước thực hiện T0 từ repo trống, mỗi bước kèm cách verify. Bám sát khi dựng T0.
- **`failure_log.md`** — taxonomy failure case (F-001…), nguyên liệu cho Production Report. Cập nhật mỗi tuần, ghi ≥3 case/tuần.
- **`README.md`** — hiện là stub, sẽ cập nhật dần sau khi dựng dự án.

Khi trạng thái tài liệu (ví dụ `docs/plan.md` §1b còn trống, các tuần ⬜ TODO) mâu thuẫn với việc "đã làm xong": đó là **cố ý** — dự án chưa verify dữ liệu thật. **Không** tự điền số liệu/kết quả chưa có; chỉ cập nhật `plan.md` §1b + trạng thái tuần **sau khi** có số thật từ `make verify`/`make eval`.

## SOURCE OF TRUTH — dự án mẫu

Một dự án mẫu đã hoàn thành một phần (T0, T2 xong) đóng vai trò chuẩn tham chiếu cho tech stack, convention, cấu trúc thư mục, và cách giải quyết vấn đề. **Nó cập nhật hàng tuần** — khi cần đối chiếu, đọc bản mới nhất (local hoặc GitHub).

- **Repo mẫu:** `../aie-rag-sample-project/` — https://github.com/ContextBoxAI/aie-rag-sample-project
- **SOURCE OF TRUTH 1:** `../aie-rag-sample-project/README.md` — https://github.com/ContextBoxAI/aie-rag-sample-project/blob/main/README.md
- **SOURCE OF TRUTH 2:** `../aie-rag-sample-project/docs/plan.md` — https://github.com/ContextBoxAI/aie-rag-sample-project/blob/main/docs/plan.md
- **Lessons:** `../aie-rag-sample-project/failure_log.md` — https://github.com/ContextBoxAI/aie-rag-sample-project/blob/main/failure_log.md

Khi cần tech stack / convention / folder structure / rules mà tài liệu của dự án này chưa nói rõ, **tham khảo dự án mẫu** rồi áp dụng cho phù hợp — đừng tự phát minh khác đi. Dự án này là bản build-from-scratch riêng, không phải bản sao; giữ nguyên các quyết định kiến trúc, được tự do khác ở chi tiết triển khai.

## Kiến trúc (đích, theo `docs/plan.md` §2 & §5)

Pipeline một chiều, mỗi lớp chỉ phụ thuộc lớp trước — dựng theo đúng thứ tự này (chi tiết ở `docs/t0.md`):

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

## Lệnh (đích — dựng trong T0, chưa tồn tại)

Toàn bộ đi qua `Makefile` (1-1 với lệnh `src/cli.py`):

```bash
make up / make down          # Bật/tắt Qdrant (Docker)
make verify                  # Tải dataset ở revision pin, assert schema + counts (verify §1b)
make golden                  # Sinh data/golden/dev.jsonl + test.jsonl (test = benchmark split)
make ingest LIMIT=500        # clean → chunk → metadata → data/processed/ (LIMIT=0 = full corpus)
make index                   # embed + upsert vào Qdrant
make search Q="..."          # tra cứu ad-hoc
make eval RETRIEVER=bm25 TOKENIZER=underthesea LABEL=...   # metric report trên split=test
make compare                 # so 2 run gần nhất, theo từng câu
make smoke                   # deliverable T0: verify→golden→ingest→index→evaluate, một lệnh
make test / make lint        # pytest / ruff
```

- **Smoke test offline:** `PROVIDER=fake make smoke` — hash embedder tất định, không cần mạng/API key. Metric nó in ra là **regression tripwire, KHÔNG phải baseline chất lượng**, không đưa vào report.
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
- `.env` không bao giờ commit; `data/raw/`, `data/processed/` git-ignored; `data/golden/` **được commit** để golden set ổn định qua các tuần.
