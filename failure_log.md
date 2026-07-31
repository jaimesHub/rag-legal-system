# Failure log

Taxonomy các failure case gặp trong quá trình xây hệ thống. Cập nhật mỗi tuần; đây là
nguyên liệu cho Production Report ở T8.

**Cột `Trạng thái`:** 🔴 chưa xử lý · 🟡 đã giảm thiểu, chưa giải quyết · ✅ đã sửa + có test chặn.

| ID | Loại | Tuần | Trạng thái |
|---|---|---|---|
| [F-001](#f-001) | Data / embedding window | T0 | 🔴 |
| [F-002](#f-002) | Data / leakage | T0 | ✅ |
| [F-003](#f-003) | Data / duplicate | T0 | ✅ |
| [F-005](#f-005) | Harness / test isolation | T0 | ✅ |
| [F-006](#f-006) | Harness / index contamination | T0 | ✅ |
| [F-011](#f-011) | Data / metadata parse | T2 | 🟡 |
| [F-012](#f-012) | Process / documentation integrity | T0 (Phase 4) | ✅ |
| [F-013](#f-013) | Harness / lint gap | T0 (Phase 3) | ✅ |
| [F-014](#f-014) | Harness / silent dilution risk | T0 (Phase 4) | 🟡 |

---

## F-001
### Điều luật dài có nguy cơ bị cắt âm thầm khi embed

**Loại:** Data / embedding window · **Tuần:** T0 · **Trạng thái:** 🔴 chưa xử lý

**Hiện tượng.** Với `chunk_strategy=article` (mặc định — corpus đã ở mức Điều), phân phối độ
dài Điều trên slice 500 văn bản gold-covering (đo từ `data/processed/ingest_audit.json`,
xác nhận lại bằng `PROVIDER=fake make smoke` Phase 4):

| Chỉ số | Giá trị (ký tự) |
|---|---|
| mean | 1.400,2 |
| p50 | 853 |
| p90 | 2.914 |
| p99 | 9.648 |
| max | **15.635** |

**Vì sao đáng lo dù slice nhỏ.** p99 và max đã gấp hơn 10 lần trung vị — đuôi phân phối rất
dày. Với cửa sổ input hữu hạn của bất kỳ embedding model nào (Gemini hay khác), các Điều ở
đuôi này có nguy cơ bị cắt bớt khi encode, và API có thể cắt input quá dài mà **không báo
lỗi** → vector chỉ đại diện cho phần đầu Điều, phần còn lại không tồn tại với retrieval. Điều
càng dài càng thường là điều quan trọng (điều khoản sửa đổi, bảng chế tài), nên rủi ro này
không tỷ lệ thuận đơn giản với số Điều bị ảnh hưởng. Và vì im lặng, nó sẽ không xuất hiện ở
bất kỳ metric nào ngoài một mức recall trần khó giải thích.

**Chưa xử lý vì** T0 chạy `PROVIDER=fake` (hash embedder không có giới hạn token) nên lỗi
này chưa *biểu hiện*, chỉ mới được *đo* qua phân phối độ dài. Nó sẽ biểu hiện ngay khi bật
Gemini.

**Hướng xử lý (T1/T3).** Khi bật Gemini, đo cụ thể bao nhiêu Điều/ký tự vượt cửa sổ token
thật của model đang dùng, rồi so các lựa chọn trên cùng golden set: (a) `chunk_strategy=khoan`
— cắt theo Khoản, giữ `doc_id` trỏ về Điều cha; (b) một model có cửa sổ context lớn hơn;
(c) cả hai. Cần một cảnh báo ở tầng ingest khi passage vượt ngưỡng token của model đang dùng
— hiện chưa có, và đó là lý do lỗi này im lặng.

---

## F-002
### 24 query id xuất hiện ở cả train và test qrels

**Loại:** Data / leakage · **Tuần:** T0 · **Trạng thái:** ✅ đã sửa

**Hiện tượng.** `qrels/train.jsonl` (2.432 query) và `qrels/test.jsonl` (788 query) giao nhau
**24 query id**. Tune trên train rồi báo cáo trên test là tự đánh giá trên dữ liệu đã thấy.

**Vì sao dễ bỏ qua.** Dataset ở format BEIR/MTEB chuẩn, tách file rõ ràng — rất dễ tin rằng
split đã sạch. Không có gì trong dataset card nhắc tới overlap này.

**Đã sửa.** `src/eval/golden.py` loại 24 id đó khỏi **dev**, giữ nguyên trong **test**
(dev = 2.408 câu). Danh sách id ghi vào `data/golden/manifest.json` để audit được. Test
chặn: `test_overlapping_queries_are_excluded_from_dev`,
`test_overlapping_queries_stay_in_the_test_split`.

---

## F-003
### `queries.jsonl` có 102 dòng trùng

**Loại:** Data / duplicate · **Tuần:** T0 · **Trạng thái:** ✅ đã sửa

**Hiện tượng.** File có 3.298 dòng nhưng chỉ **3.196 `_id` duy nhất**. Nạp thành list rồi
lặp là đếm trùng 102 câu → mọi macro-average bị lệch theo hướng không kiểm soát được.

**Đã sửa.** `load_queries` trả `dict[str, Query]` dedupe theo `_id` (giữ dòng đầu) và trả
kèm số dòng đã bỏ; `make verify` in ra con số này; ghi vào `manifest.json`.

**Ghi chú thêm.** File JSONL gốc dùng khoá `_id`, còn config parquet MTEB dùng `id` — loader
nhận cả hai. Nếu chỉ đọc một khoá thì hoặc mất toàn bộ query, hoặc phải đổi nguồn dữ liệu.

---

## F-005
### Test suite ghi vào repo thật

**Loại:** Harness / test isolation · **Tuần:** T0 · **Trạng thái:** ✅ đã sửa

**Hiện tượng.** Hai test "file chưa tồn tại thì phải raise `FileNotFoundError`" fail với
*DID NOT RAISE* — vì file **đã tồn tại**: các test trước đó đã ghi `data/golden/dev.jsonl`
và `data/processed/passages.jsonl` vào **repo thật**.

**Vì sao `monkeypatch.chdir(tmp_path)` không đủ.** `Settings` derive mọi path từ
`ROOT = Path(__file__).parents[1]` — hằng số tính lúc import, hoàn toàn không phụ thuộc cwd.
Đổi cwd không đổi được gì.

**Vì sao đáng ghi lại.** Hai test fail chỉ là *triệu chứng*. Bệnh là test suite làm bẩn
dataset của dự án — nếu hai test kia không tồn tại, lỗi này sẽ âm thầm và có thể dẫn tới
đánh giá trên golden set do test sinh ra.

**Đã sửa.** Thêm field `base_dir` vào `Settings`, mọi path derive từ nó; fixture truyền
`base_dir=tmp_path`. Dọn file đã lẫn vào repo.

---

## F-006
### Vector fake có thể nhiễm vào collection thật

**Loại:** Harness / index contamination · **Tuần:** T0 · **Trạng thái:** ✅ đã sửa

**Hiện tượng.** Tên collection derive từ `embed_model` + `embed_dim`. Chạy `PROVIDER=fake`
mà giữ `EMBED_MODEL=gemini-embedding-001` → vector hash được upsert vào
`legal_gemini_embedding_001_768`, đúng collection mà lần chạy Gemini thật sẽ dùng. Vì
`point_id` là UUID5 của `passage_id`, chúng **ghi đè đúng chỗ** — không lỗi, không cảnh báo,
chỉ là một index trộn hai loại vector khác hoàn toàn về ngữ nghĩa.

**Phát hiện lúc nào.** Trước khi chạy thật, khi đang rà lại lệnh smoke — chưa gây hậu quả.

**Đã sửa.** `provider == "fake"` → tên collection dùng `fake-embedding`, tách hẳn:
`legal_fake_embedding_768`. Test chặn: `test_fake_provider_gets_its_own_collection`.

**Nguyên tắc rút ra.** Tên collection phải phản ánh **vector thực sự nằm trong đó**, không
phải cấu hình mong muốn. Áp dụng lại khi thêm sparse vector ở T4.

---

## F-011
### 173 Điều không parse được metadata

**Loại:** Data / metadata parse · **Tuần:** T2 · **Trạng thái:** 🟡 đã đếm, chưa xử lý

**Hiện tượng.** Ingest toàn corpus: **173/61.425 (0,3%)** corpus id không khớp dạng
`<số>/<năm>/<mã>+<chỉ số Điều>`, nên `doc_type=unknown`, `year=None`, `issuer=None`.

Trên slice 500 văn bản của T0 con số này là **0** — lỗi chỉ lộ ra ở quy mô đầy đủ. Một lời
nhắc rằng slice nhỏ không chỉ làm metric lạc quan, nó còn **ẩn luôn các lớp lỗi**.

**Vì sao cần xử lý trước T5.** `doc_type`, `year`, `issuer` chính là các trường T5 sẽ dùng để
filter. Một filter `year >= 2020` sẽ **âm thầm loại bỏ** cả 173 văn bản này, và không có gì
trong kết quả cho thấy điều đó đã xảy ra.

**Đã có.** Không raise; đếm trong `data/processed/ingest_audit.json` và in ra khi ingest.

**Cần làm ở T5.** Xem 173 id đó thực sự có dạng gì, mở rộng parser hoặc chấp nhận và làm cho
filter **tường minh** về việc loại bỏ bản ghi thiếu metadata (thay vì im lặng).

---

## F-012
### `failure_log.md` kế thừa từ dự án mẫu chứa entry sai lệch — đã dọn theo quyết định của user

**Loại:** Process / documentation integrity · **Tuần:** T0 (phát hiện Phase 4, xử lý sau đó) · **Trạng thái:** ✅ đã sửa

**Phát hiện (Phase 4).** Khi chạy `PROVIDER=fake make smoke` (Phase 4) và đối chiếu
`data/processed/ingest_audit.json` thật:

| Chỉ số | F-001 (bản cũ, có sẵn trong file từ commit đầu) | Đo thật (smoke Phase 4 + `ingest_audit.json`) |
|---|---|---|
| p50 | 888 | **853** |
| p90 | 3.515 | **2.914** |
| p99 | 9.954 | **9.648** |
| max | **51.862** ký tự | **15.635** |
| ví dụ Điều dài nhất | `20/2012/qh13+1` | (không xuất hiện trong audit thật) |

Số "đo thật" khớp tuyệt đối với `docs/week0/phase2-report.md` (viết sau khi chạy ingest thật
ở Phase 2). Số trong F-001 bản cũ thì không khớp bất kỳ lần chạy nào của dự án này.

`git log -- failure_log.md` cho thấy toàn bộ F-001…F-011 (bản cũ) đã được commit trong
**commit đầu tiên** của repo (`5aeade9`, chỉ có tài liệu, *trước khi* bất kỳ dòng code nào
tồn tại) — tức **không thể** sinh ra từ một lần `make ingest` thật của dự án này. File này copy
phần lớn từ dự án mẫu (`../aie-rag-sample-project`). Một số entry (F-002 leakage=24, F-003
duplicate=102, F-011 metadata=173) tình cờ khớp đúng số thật đo được sau này ở Phase 2 (có thể
vì cùng dataset với dự án mẫu), nhưng F-001 thì lệch hẳn, và F-004/F-007–F-010 (bản cũ) mô tả
kết quả BM25/T2 (`notebooks/02_lexical_search.ipynb`, `src/retrieve/bm25.py`) — những file/công
việc này **chưa tồn tại** trong repo ở T0 (`find` không thấy). Đây đúng là loại lỗi mà
CLAUDE.md cấm tuyệt đối: "Không tự điền số liệu/kết quả chưa có" — nhưng nó nằm trong file từ
trước khi Phase 1 bắt đầu, không phải do agent nào trong 4 phase build T0 này viết.

**Xử lý (theo quyết định của user, sau Phase 4).**
- **F-001** viết lại với số đo thật từ `data/processed/ingest_audit.json` (mean 1.400,2 /
  p50 853 / p90 2.914 / p99 9.648 / max 15.635 ký tự, slice 500 văn bản gold-covering); giữ
  nguyên bản chất mối lo (Điều dài có nguy cơ vượt cửa sổ embedding, ẩn dưới `PROVIDER=fake`),
  bỏ mọi số liệu/dẫn chứng không kiểm chứng được (tỷ lệ Điều vượt cửa sổ token, ví dụ
  `20/2012/qh13+1`); trạng thái giữ 🔴 vì đây vẫn là rủi ro thật, chưa xử lý.
- **F-004, F-007, F-008, F-009, F-010** — xoá hoàn toàn (cả hàng bảng lẫn mục `## F-00x`):
  mô tả công việc BM25/T2 chưa làm trong repo này và trích dẫn file không tồn tại
  (`src/retrieve/bm25.py`, `notebooks/02_lexical_search.ipynb`).
- **F-002, F-003, F-005, F-006, F-011, F-013, F-014** — đối chiếu lại với dữ liệu/code thật
  hiện có trong repo, khớp nên giữ nguyên nội dung; dọn các tham chiếu chéo còn sót lại trỏ
  tới entry đã xoá.

**Nguyên tắc rút ra.** Áp dụng đúng protocol đã dùng cho sự cố `CLAUDE.md` ở Phase 3 (coi nội
dung lạ là **untrusted** cho tới khi xác minh được nguồn gốc): trước khi trích số liệu từ bất
kỳ file "kết quả" nào trong repo để đưa vào report, luôn `git log`/`git blame` để xác nhận số
đó sinh ra **sau** dòng code đo được nó, không phải nằm sẵn từ commit tài liệu ban đầu.

---

## F-013
### `ruff format --check` fail vì code Phase 2 chưa format

**Loại:** Harness / lint gap · **Tuần:** T0 (Phase 3) · **Trạng thái:** ✅ đã sửa

**Hiện tượng.** Lần chạy `make lint` đầu tiên ở Phase 3 fail ở bước `ruff format --check`:
`src/index/qdrant_store.py` (viết ở Phase 2) có một lời gọi `warnings.filterwarnings(...)` bị
tách thành 3 dòng, không đúng style `ruff format` mong đợi.

**Vì sao đáng ghi lại.** `ruff check` (lint quy tắc) đã sạch từ Phase 2 — chỉ `ruff format
--check` (format thuần) mới bắt được lỗi này. Hai lệnh khác mục đích và phải chạy **cả hai**
trong CI/`make lint`, nếu chỉ chạy `ruff check` thì lỗi format kiểu này lọt qua nhiều tuần mà
không ai biết.

**Đã sửa.** Chạy `ruff format` gộp lời gọi về 1 dòng (thuần format, không đổi logic); xác nhận
lại `pytest` vẫn 93 passed sau khi format.

**Nguyên tắc rút ra.** `make lint` phải luôn chạy cả `ruff check` **và** `ruff format --check`
— coi đây là hai gate độc lập, không phải một cái suy ra được từ cái kia.

---

## F-014
### Gold-coverage forcing hỏng sẽ không báo lỗi — chỉ âm thầm giảm số câu evaluate về gần 0

**Loại:** Harness / silent dilution risk · **Tuần:** T0 (Phase 4) · **Trạng thái:** 🟡 đã giảm thiểu, chưa có test chặn regressive

**Hiện tượng.** Concern mở từ Phase 3: liệu việc ép gold-coverage ở `ingest` (bước 10) có thực
sự áp dụng **trước** khi `evaluate` lọc golden test split theo `only_indexed=True` hay không —
nếu thứ tự này hỏng, `evaluate` vẫn chạy **không lỗi**, chỉ trả về một tập câu bị pha loãng gần
hết. Chạy `PROVIDER=fake make smoke` (Phase 4) xác nhận: `Evaluating 573/788 queries — the
rest have gold documents outside the current ingest slice` — 573 là con số hợp lý (377 câu
test được `plan_gold_coverage` chủ đích phủ, cộng thêm các câu khác tình cờ trỏ vào 250 gold
doc hoặc 250 distractor), không gần 0, nên forcing đang hoạt động đúng.

**Vì sao vẫn đáng lo dù lần này đúng.** Không có gì trong `evaluate` **cảnh báo** nếu con số
573 tụt xuống, ví dụ, 12 — một refactor vô tình đổi thứ tự `build_passages`/`plan_gold_coverage`
sẽ cho ra một smoke test **chạy xong, không lỗi, in bảng metric trông bình thường**, nhưng
metric đó được tính trên vài câu thay vì hàng trăm câu, và không ai biết trừ khi đọc kỹ dòng
log số lượng.

**Đã giảm thiểu.** Dòng log `Evaluating N/788 queries — ...` được in mỗi lần chạy, nên con số
573 này giờ trở thành **regression tripwire** thứ hai (bên cạnh bảng metric) — nếu N tụt mạnh ở
lần chạy sau, đó là dấu hiệu ingest gold-coverage đã hỏng trước khi nhìn tới metric.

**Cần làm.** Thêm assertion/ngưỡng cứng trong `evaluate` hoặc test tích hợp: fail rõ ràng nếu
`evaluated_queries` tụt dưới một tỷ lệ tối thiểu so với kỳ vọng, thay vì chỉ log và tiếp tục —
cùng nguyên tắc chung: luôn hỏi "nó trả về gì khi không tìm thấy gì?" trước khi tin một hệ
thống chạy "không lỗi".
