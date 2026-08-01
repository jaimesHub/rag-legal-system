# RAG Tra cứu Luật Việt Nam

Hệ thống retrieval cho văn bản pháp luật Việt Nam, xây theo hướng **đo được – gỡ lỗi được –
cải thiện được** (lộ trình 8 tuần T0→T8). Kế hoạch đầy đủ (kiến trúc, roadmap, deliverables,
eval harness, rủi ro, nghi thức hàng tuần) ở [`docs/plan.md`](docs/plan.md) — đó là tài liệu
gốc, mọi thứ khác chỉ trỏ vào nó. Report mỗi tuần trong [`reports/`](reports/.gitkeep), failure case
trong [`failure_log.md`](failure_log.md).

**Trạng thái:** T0 ✅ DONE ([reports/week0.md](reports/week0.md)) — skeleton, Docker Qdrant,
lớp abstraction provider, smoke test đường dây end-to-end. T1 (Eval Harness đầy đủ:
DeepEval + LLM-as-judge) **chưa bắt đầu**. Chi tiết trạng thái từng tuần ở
[`docs/plan.md` §3](docs/plan.md#3-lộ-trình-8-tuần).

**Chưa có baseline chất lượng.** Số duy nhất tồn tại hiện nay là smoke tripwire của T0
(`PROVIDER=fake`, embedder hash không có ngữ nghĩa, chạy trên slice 500/61.425 tài liệu) —
**không phải** số để so sánh retriever, chỉ để phát hiện regression khi refactor. Baseline
thật đầu tiên (BM25 + underthesea, toàn bộ 61.425 Điều, cả 788 câu test) đến ở **T2**.

---

## Quickstart

Cần: [uv](https://docs.astral.sh/uv/), Docker.

```bash
uv sync                 # cài deps
cp .env.example .env    # điền GEMINI_API_KEY nếu muốn chạy Gemini thật (chưa cần ở T0/T1)
make up                 # Qdrant tại localhost:6333
PROVIDER=fake make smoke  # verify → golden → ingest(500) → index → evaluate, một lệnh, offline
```

`PROVIDER=fake` là hash embedder tất định — không cần mạng ngoài Hugging Face Hub (dataset tự
tải + cache vào `data/raw/`, git-ignored) và không cần `GEMINI_API_KEY`. Nó ghi vào collection
riêng (`legal_fake_embedding_768`) nên **không thể** nhiễm vào index Gemini thật (bất biến #2
bên dưới). Metric nó in ra là tripwire, không phải chất lượng — xem
[reports/week0.md](reports/week0.md) để biết vì sao con số đó cao bất thường (Recall@10 ≈ 0,96
trên 573/788 câu).

## Các lệnh

Toàn bộ đi qua `Makefile`, 1-1 với `src/cli.py` (`make help` liệt kê có mô tả):

| Lệnh | Việc |
|---|---|
| `make up` / `make down` / `make logs` | Bật/tắt/xem log Qdrant |
| `make sync` | `uv sync` |
| `make fetch` | (tuỳ chọn) tải trước dataset vào `data/raw/` — các lệnh khác tự tải khi cần |
| `make verify` | Tải dataset ở revision pin, assert schema + counts |
| `make golden` | Sinh `data/golden/dev.jsonl` + `test.jsonl` (`test` là split benchmark) |
| `make ingest LIMIT=500` | clean → chunk → metadata → `data/processed/` (`LIMIT=0` = full corpus, dùng từ T2) |
| `make index` | Embed + upsert vào Qdrant |
| `make search Q="..."` | Tra cứu ad-hoc (retriever vector — bm25/hybrid đến ở T2/T4) |
| `make eval RETRIEVER=vector LABEL=...` | Metric report trên `split=test` |
| `make smoke` | Deliverable T0: verify→golden→ingest→index→evaluate, một lệnh |
| `make compare-sample WEEK=N` | Scorecard 7 trục so với dự án mẫu (xem bên dưới) |
| `make test` / `make lint` / `make fmt` | pytest / ruff check+format / autoformat |

Chưa có `make compare` (per-query 2-run nội bộ), `make tokens`, `make sweep`, hay dashboard —
những lệnh đó thuộc T1/T2/T8, chưa tồn tại.

---

## Kiến trúc

Pipeline một chiều `ingest → index → retrieve → rank → generate`, mỗi lớp đo bằng eval
harness; chi tiết đầy đủ + sơ đồ ở [`docs/plan.md` §2](docs/plan.md#2-kiến-trúc-pipeline-end-to-end).

```
config/settings.py   .env → {provider, embed_model, dim, collection, dataset_revision, ...}
src/providers/        EmbeddingProvider.embed(texts, task_type) · LLMProvider.complete/judge
                       gemini.py (thật) · fake.py (offline, tất định) · registry.py (config → impl)
src/ingest/            loader (HF pin) · clean (NFC) · metadata · chunk (Điều/Khoản) · pipeline
src/index/             Qdrant: named dense vector "dense", payload index cho filter (T5)
src/retrieve/          base.py = contract retrieve(query, k) → [(doc_id, score)] · vector.py
src/eval/              golden (dev/test + leakage guard) · metrics · harness (per-query) · compare*
src/cli.py             entrypoint cho mọi target Makefile (Typer)
```

*`src/rank/`, `src/generate/`, `dashboard/`, BM25/hybrid retriever chưa tồn tại — đến ở
T2 trở đi theo [roadmap](docs/plan.md#3-lộ-trình-8-tuần).*

**Bốn bất biến**, cưỡng chế bằng code, không bằng quy ước:

1. **`test` là split benchmark của mọi tuần; `dev` không dùng để eval** — để dành cho fine-tune
   embedding sau này, không có khái niệm "tune trên dev rồi mở test" cần bảo vệ ở đây.
2. **Đổi embedding = re-index toàn bộ.** Tên collection derive từ `embed_model` + `embed_dim`;
   `provider=fake` dùng model-slug riêng (`fake-embedding`) để vector giả không nhiễm collection thật.
3. **Không leakage.** 24 query id giao nhau train↔test bị loại khỏi `dev`, giữ nguyên trong `test`.
4. **Không so hai tập câu khác nhau.** Mọi so sánh với baseline chạy trên đủ tập câu `test`.

## Dataset

[`GreenNode/zalo-ai-legal-text-retrieval-vn`](https://huggingface.co/datasets/GreenNode/zalo-ai-legal-text-retrieval-vn)
(format BEIR/MTEB), pin revision `12d76d4d…`: 61.425 Điều (corpus) · 3.196 câu hỏi unique
(3.298 dòng, 102 trùng `_id`) · qrels test 793 nhãn / 788 câu. Corpus id dạng
`01/2009/tt-bnn+1` = `<số>/<năm>/<mã>+<chỉ số Điều>` → suy ra loại văn bản, năm, cơ quan ban
hành. 4 giả định ban đầu về dataset đã xác nhận bằng dữ liệu thật ở T0 — chi tiết ở
[`docs/plan.md` §1b](docs/plan.md#1b-xác-nhận-dữ-liệu-thật-t0).

---

## So sánh mức hoàn thành với dự án mẫu

Dự án này xây song song với một **dự án mẫu** tham chiếu
(`../aie-rag-sample-project` — https://github.com/ContextBoxAI/aie-rag-sample-project). Có thể
tự chạy so sánh theo từng tuần (T0, T1, …) bằng `make compare-sample`. Chi tiết đầy đủ (rubric
7 trục, guard cùng-cấu-hình, cách đọc scorecard) ở
[`docs/comparison-framework.md`](docs/comparison-framework.md); tóm tắt cách dùng:

### Bước 0 — Chuẩn bị (2 repo cạnh nhau)
```bash
git clone <repo-này> rag-legal-system
git clone https://github.com/ContextBoxAI/aie-rag-sample-project   # đặt cạnh nhau
cd rag-legal-system && uv sync && make up        # Qdrant qua Docker
```
> `compare-sample` mặc định đọc repo mẫu ở `../aie-rag-sample-project` (hai repo đặt cạnh nhau).
> Đổi vị trí đó bằng `--sample-root PATH`, truyền qua `CS_ARGS` — ví dụ
> `make compare-sample WEEK=2 CS_ARGS="--sample-root /duong/dan/aie-rag-sample-project"`.
> `--sample-root` trỏ tới **bản checkout git** của mẫu và chỉ dùng cho hai việc: (1) **trục 1 —
> cấu trúc**: chụp snapshot bộ module của mẫu trên đĩa để so scope (`structural_snapshot`); (2)
> `--validate-sample`: chạy `git -C <sample-root> rev-parse HEAD` để cảnh báo nếu HEAD mẫu đã đi
> trước `meta.sample_commit` ghi trong YAML (dấu hiệu số đang chép có thể đã cũ). **Số benchmark
> của mẫu KHÔNG đọc từ đây** mà từ [`docs/sample-baselines.yaml`](docs/sample-baselines.yaml) (đã
> commit) — nên nếu chỉ cần so metric thì không bắt buộc có repo mẫu trên máy; `--sample-root`
> chỉ cần khi muốn chấm trục cấu trúc hoặc chạy `--validate-sample`.

### Bước 1 — Sinh số của dự án này cho tuần cần so
- **Tuần cấu trúc (T0/T1):** `PROVIDER=fake make smoke` (offline) là đủ.
- **Tuần metric (T2+):** `make ingest LIMIT=0 && make index && make eval RETRIEVER=<bm25|vector|hybrid> LABEL=tN-baseline` (cần `GEMINI_API_KEY` từ T3).

### Bước 2 — Chạy so sánh
```bash
make compare-sample WEEK=0                              # scorecard 7 trục + ghi JSON
make compare-sample WEEK=2 CS_ARGS="--emit-md"         # + block markdown dán vào reports/weekN.md
make compare-sample WEEK=2 CS_ARGS="--validate-sample" # cảnh báo nếu số mẫu đã cũ (HEAD ≠ sample_commit)
```

### Bước 3 — Đọc & tự double-check
- **4 ký hiệu:** ✅ đạt · 🟡 một phần / **cần người tự phán** · 🔴 behind · ➖ N/A tuần này.
- **Tự tay xác nhận** trục 2 (chạy `make test`), 4 (report có đạt nghi thức §8?), 7 (git landing) — tool chỉ đếm nên để 🟡.
- **Guard cùng cấu hình:** metric chỉ hiện khi split=test + revision pin + 788 câu + full corpus 61.425 — nếu không → ➖ kèm lý do (không so slice với full).
- **Bẫy:** chạy cho tuần *chưa làm* → `overall: behind` chỉ vì report/failure-log chưa có, **không phải tụt hậu**.
- **Double-check:** chạy lại (tất định) · đọc `artifacts/compare_sample/*.json` · đối chiếu số mẫu với `reports/week2.md` của mẫu · tái lập `make eval`.

### Ý nghĩa "hoàn thành so với mẫu"
- **Chuẩn đạt:** có **số thật tái lập được + giải thích per-query** = ĐẠT. **Vượt mẫu là bonus, không phải cửa.**
- T0/T1 so **cấu trúc/quy trình**; **head-to-head metric bắt đầu từ T2** (mẫu Recall@10 0,8610). Mẫu hiện rộng hơn (đã T2+) là **kỳ vọng** vì đi trước — không phải dự án này tụt hậu.

---

## Ghi chú

- `.env` không bao giờ commit; `GEMINI_API_KEY` không log, không in.
- `data/raw/` và `data/processed/` là dữ liệu tái lập được → git-ignored. `data/golden/`
  **được commit** để golden set ổn định qua các tuần.
- Cổng: Qdrant `6333` (HTTP/dashboard) / `6334` (gRPC). `8000–8002`/`3000–3001` bị project
  contextbox khác chiếm; T8 dùng `8010` (API) + `8501` (dashboard).
