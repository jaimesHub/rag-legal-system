# Phase 1 (T0 bước 1–6) — Tóm tắt

**Phạm vi:** Hoàn tất bước 1–6 trong `docs/week0/t0.md` — scaffold cơ sở, cấu hình, schemas, và lớp providers.

Mục tiêu: xây dựng nền tảng cho pipeline RAG, đảm bảo mọi import đều hoạt động, cấu hình tách rời môi trường, và các provider (Gemini thật + Fake offline) sẵn sàng cho các bước tiếp theo (ingest, index, retrieve).

---

## Đã có sẵn và đã review đạt (không cần sửa)

| Thành phần | Chi tiết |
|---|---|
| **pyproject.toml + uv.lock** | 55 packages, quản lý deps bằng `uv` |
| **docker-compose.yml** | Qdrant local port 6333 (HTTP), 6334 (gRPC) |
| **Makefile** | 1-1 với src/cli.py, toàn bộ lệnh đi qua đây |
| **.env.example + .gitignore** | Tách `.env`, git-ignore `data/raw/`, `data/processed/` |

### config/settings.py
- `base_dir` là **field không hard-code** — mọi path (raw_dir, processed_dir, golden_dir, artifacts_dir, reports_dir) derive qua property  
  → **Tránh bẫy #1**: không bẫy `Path(__file__)`
- `collection_name` = `legal_<model-slug>_<dim>`  
  → Provider "fake" có slug riêng (`fake-embedding`) để tách vector giả khỏi collection thật  
  → **Tránh bẫy #2**: không nhiễm leakage F-006
- `dataset_repo_id` = `GreenNode/zalo-ai-legal-text-retrieval-vn` với `dataset_revision` pin commit hash

### src/schemas.py
- **LegalMetadata** — metadata trích xuất từ tài liệu
- **Passage** — passage_id, doc_id, title, text, embed_text, metadata (contract chính)
- **Query** — query text + doc_id gốc
- **GoldenExample** — query + graded passages (dev/test split)
- **SplitStats** — số lượng trên mỗi split

### src/providers/
| Module | Chức năng |
|---|---|
| **base.py** | Protocol `EmbeddingProvider` / `LLMProvider` + TaskType Literal |
| **fake.py** | Hashed bag-of-words embedder L2-normalized, tất định + FakeLLMProvider (không cần mạng) |
| **gemini.py** | google-genai client, tenacity retry, per-input Content wrapping, task_type hint |
| **registry.py** | config → impl, tách role judge/generator |

---

## Mới tạo trong Phase 1

### Stub modules (importable, chưa có logic)
```
src/ingest/
  ├── loader.py (docstring → Phase 2)
  ├── clean.py
  ├── metadata.py
  ├── chunk.py
  └── pipeline.py

src/index/
  └── qdrant_store.py

src/retrieve/
  ├── base.py (contract)
  └── vector.py

src/eval/
  ├── golden.py
  ├── metrics.py
  └── harness.py
```

### Mục đích import thử
- `from src.ingest import ...` ✓
- `from src.index import ...` ✓
- `from src.retrieve import ...` ✓
- `from src.eval import ...` ✓

### src/cli.py
- Typer stub, 1 placeholder command để `--help` chạy

### Cấu trúc thư mục + .gitkeep
```
data/
  ├── raw/ (git-ignored, dataset HuggingFace sẽ vào đây)
  ├── processed/ (git-ignored, ingest output)
  └── golden/ (COMMIT để ổn định golden set)

reports/ (eval results per tuần)

tests/
  ├── conftest.py (fixture settings + tmp_path)
  ├── unit/
  └── integration/
```

---

## Kết quả verify (đã chạy thật)

| Kiểm tra | Kết quả |
|---|---|
| `uv sync` | ✓ Thành công, 55 packages |
| `import config, src` | ✓ OK |
| Toàn bộ stub modules | ✓ Import được |
| **Fake embedder** | ✓ Shape [128,128], norm [1.0,1.0], deterministic |
| **Collection name (Gemini)** | ✓ `legal_gemini_embedding_001_768` |
| **Collection name (Fake)** | ✓ `legal_fake_embedding_768` |

### Offline smoke (PROVIDER=fake)
- Embedder không cần API key
- Hash tất định → reproducible metric (tripwire, không phải baseline chất lượng)

---

## Chưa làm (để lại Phase 2)

- [ ] tests/unit/ và tests/integration/ — test logic thật (Phase 3)
- [ ] Docker Qdrant (`make up`) — cần Phase 2 (retrieve)
- [ ] Dataset loader + `make verify` — cần mạng HuggingFace (Phase 2)
- [ ] make smoke — cần đầy đủ pipeline (Phase 2 + 3)

---

## Bước tiếp theo → Phase 2

**Phase 2 = t0.md bước 7–13:**

1. **Loader** (`src/ingest/loader.py`) — tải dataset từ HF pin revision
2. **`make verify`** — assert schema + counts (cần mạng)
3. **Clean, metadata, chunk** — xử lý corpus
4. **`make golden`** — sinh dev.jsonl + test.jsonl (24 query leakage filter)
5. **Pipeline + ingest** — đưa vào data/processed/
6. **`make index`** — upsert vào Qdrant (cần `make up`)
7. **Retrieve layer** — vector retriever (BM25/hybrid là T2, chưa làm ở T0)
8. **Metrics + harness** — đánh giá per-query
9. **`make eval`** — metric report (regression tripwire, chưa phải baseline chất lượng)

**Đích:** có được `make smoke` (verify → golden → ingest → index → eval, một lệnh).
