# RAG Tra cứu Luật Việt Nam

Hệ thống Retrieval văn bản pháp luật VN, xây theo hướng **đo được – gỡ lỗi được – cải thiện được**
(lộ trình 8 tuần T0→T8). Tài liệu điều hành: `docs/plan.md` (kế hoạch), `docs/roadmap-progress.md`
(tiến độ T0 + kế hoạch T1–T8), `docs/comparison-framework.md` (khung so sánh với dự án mẫu).

## So sánh mức hoàn thành với dự án mẫu

Dự án này xây song song với một **dự án mẫu** tham chiếu
(`../aie-rag-sample-project` — https://github.com/ContextBoxAI/aie-rag-sample-project). Có thể tự
chạy so sánh theo từng tuần (T0, T1, …) bằng `make compare-sample`. Chi tiết đầy đủ ở
`docs/comparison-framework.md`; tóm tắt cách dùng:

### Bước 0 — Chuẩn bị (2 repo cạnh nhau)
```bash
git clone <repo-này> rag-legal-system
git clone https://github.com/ContextBoxAI/aie-rag-sample-project   # đặt cạnh nhau
cd rag-legal-system && uv sync && make up        # Qdrant qua Docker
```
> `compare-sample` mặc định đọc mẫu ở `../aie-rag-sample-project` (đổi bằng `--sample-root`). Số
> chuẩn của mẫu lấy từ `docs/sample-baselines.yaml` (đã commit), **không** cần chạy eval của mẫu.

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
- T0/T1 so **cấu trúc/quy trình**; **head-to-head metric bắt đầu từ T2** (mẫu Recall@10 0.8610). Mẫu hiện rộng hơn (đã T2+) là **kỳ vọng** vì đi trước — không phải dự án này tụt hậu.
