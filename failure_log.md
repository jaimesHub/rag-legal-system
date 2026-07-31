# Failure log

Taxonomy các failure case gặp trong quá trình xây hệ thống. Cập nhật mỗi tuần; đây là
nguyên liệu cho Production Report ở T8.

**Cột `Trạng thái`:** 🔴 chưa xử lý · 🟡 đã giảm thiểu, chưa giải quyết · ✅ đã sửa + có test chặn.

| ID | Loại | Tuần | Trạng thái |
|---|---|---|---|
| [F-001](#f-001) | Data / embedding window | T0 | 🔴 |
| [F-002](#f-002) | Data / leakage | T0 | ✅ |
| [F-003](#f-003) | Data / duplicate | T0 | ✅ |
| [F-004](#f-004) | Retrieval / lexical confusion | T0 → T2 | 🔴 *(đã định lượng, xem F-010)* |
| [F-005](#f-005) | Harness / test isolation | T0 | ✅ |
| [F-006](#f-006) | Harness / index contamination | T0 | ✅ |
| [F-007](#f-007) | Metric / score incomparability | T2 | 🟡 |
| [F-008](#f-008) | Library / silent zero-score results | T2 | ✅ |
| [F-009](#f-009) | Method / aggregate hides churn | T2 | ✅ |
| [F-010](#f-010) | Retrieval / article resolution | T2 | 🔴 **nút thắt chính** |
| [F-011](#f-011) | Data / metadata parse | T2 | 🟡 |

---

## F-001
### Điều luật dài bị cắt âm thầm khi embed

**Loại:** Data / embedding window · **Tuần:** T0 · **Trạng thái:** 🔴 chưa xử lý

**Hiện tượng.** Với `chunk_strategy=article` (mặc định — corpus đã ở mức Điều), một số Điều
dài hơn cửa sổ input của embedding model. Trên slice 500 Điều:

| Chỉ số | Giá trị |
|---|---|
| p50 / p90 / p99 độ dài | 888 / 3.515 / 9.954 ký tự |
| max | **51.862 ký tự** (`20/2012/qh13+1`, title chỉ là "Điều 1.") |
| Vượt cửa sổ 2.048 token của `gemini-embedding-001` (~7.168 ký tự) | 15 Điều = **3,0%** |
| Tỷ lệ **ký tự** nằm ngoài cửa sổ | **11,7%** tổng text |
| Vượt cửa sổ 8.192 token của `gemini-embedding-2` | 2 Điều |

**Vì sao nghiêm trọng hơn con số 3% gợi ý.** API cắt input quá dài mà **không báo lỗi** →
vector đại diện cho 1/7 đầu của điều luật, phần còn lại không tồn tại với retrieval. Điều
càng dài càng thường là điều quan trọng (điều khoản sửa đổi, bảng chế tài), nên 3% Điều này
gánh nhiều hơn 3% giá trị. Và vì im lặng, nó sẽ không xuất hiện ở bất kỳ metric nào ngoài
một mức recall trần khó giải thích.

**Chưa xử lý vì** T0 chạy `PROVIDER=fake` (hash embedder không có giới hạn token) nên lỗi
này chưa *biểu hiện*, chỉ mới được *đo*. Nó sẽ biểu hiện ngay khi bật Gemini.

**Hướng xử lý (T3).** So ba lựa chọn trên cùng golden set: (a) `chunk_strategy=khoan` —
cắt theo Khoản, giữ `doc_id` trỏ về Điều cha; (b) `gemini-embedding-2` với cửa sổ 8.192
token; (c) cả hai. Cần một cảnh báo ở tầng ingest khi passage vượt ngưỡng token của model
đang dùng — hiện chưa có, và đó là lý do lỗi này im lặng.

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

## F-004
### Retrieval nhầm theo từ chung, không theo ý

**Loại:** Retrieval / lexical confusion · **Tuần:** T0 · **Trạng thái:** 🟡 đã giảm thiểu

**Hiện tượng.** Query *"Mức phạt khi quay đầu xe ô tô trên đường cao tốc"* → top-1 là
`01/2010/tt-bng+13` **"Điều 13. Quốc kỳ Việt Nam trên xe riêng của người đứng đầu cơ quan
đại diện"** (score 0.2469), trong khi Điều đúng về xử phạt giao thông xếp thứ 2 (0.2446).
Khoảng cách score chỉ **0,9%**.

Các miss hoàn toàn ở k=10 cho thấy cùng một hình mẫu, và một biến thể đáng chú ý hơn:

| Query | Expected | Got (top-3) |
|---|---|---|
| Bằng lái xe bị tước nhưng sắp hết hạn có được cấp đổi không? | `100/2019/nđ-cp+81` | `100/2019/nđ-cp+17`, `+37`, `+16` |
| Không thỏa thuận về bồi thường thiệt hại có được bồi thường không? | `91/2015/qh13+418` | `91/2015/qh13+585`, … |

**Vì sao đây là failure mode nguy hiểm nhất của dataset này.** Hai dòng trên retrieve **đúng
văn bản luật, sai Điều** — cùng `doc_key`, lệch `article_index`. Đây không phải lỗi "không
tìm thấy tài liệu" mà là lỗi **phân giải trong một tài liệu**, và nó sẽ không được khắc phục
bằng cách làm embedding tốt hơn ở mức văn bản. Nó cần tín hiệu ở mức Điều/Khoản (chunking
T3) hoặc rerank đọc kỹ nội dung (T4).

**Đã giảm thiểu một phần.** `dedupe_by_doc` + oversample ×3 để nhiều Khoản của một Điều
không chiếm hết top-k.

**Lưu ý khi đọc.** T0 dùng hash embedder nên phần "nhầm theo từ chung" bị phóng đại. Nhưng
hình mẫu *đúng văn bản, sai Điều* là thuộc tính của dataset, không phải của embedder — cần
kiểm chứng lại ở T1 với Gemini và **theo dõi riêng như một metric** (tỷ lệ miss mà
`doc_key` đúng nhưng `article_index` sai).

**✅ Đã kiểm chứng ở T2 và đúng.** Trên toàn corpus với BM25 thật, **65% số miss** là đúng
văn bản sai Điều. Giả thuyết "thuộc tính của dataset, không phải của embedder" được xác
nhận. Xem [F-010](#f-010) — nó đã trở thành nút thắt chính của hệ thống.

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

## F-007
### Điểm BM25 không so sánh được giữa các cài đặt

**Loại:** Metric / score incomparability · **Tuần:** T2 · **Trạng thái:** 🟡 đã hiểu, cần nhớ

**Hiện tượng.** Bản BM25 viết từ đầu trong notebook (công thức sách giáo khoa) cho điểm
`6,247748` trên cùng dữ liệu mà `bm25s` cho `2,499099`. Tỷ lệ đúng bằng **2,5 = k1 + 1**.

**Nguyên nhân.** Lucene — và `bm25s` khi `method="lucene"` — **cố tình bỏ** thừa số `(k1+1)`
ở tử số:

```
sách giáo khoa :  idf · tf·(k1+1) / (tf + k1·(1-b+b·dl/avgdl))
Lucene/bm25s   :  idf · tf        / (tf + k1·(1-b+b·dl/avgdl))
```

`(k1+1)` là hằng số với mọi document và mọi term ⇒ **không thể đổi thứ hạng**, chỉ đổi thang
điểm. Bỏ nó tiết kiệm một phép nhân.

**Vì sao đáng ghi lại.** Không phải bug, nhưng là cái bẫy thật:

1. **Đừng đặt ngưỡng cứng lên điểm BM25 thô** (kiểu "chỉ nhận hit nếu score > 5"). Ngưỡng đó
   vô nghĩa khi đổi thư viện, đổi `method`, hoặc thậm chí đổi `k1`.
2. Đừng so điểm giữa hai hệ thống retrieval. Chỉ **thứ hạng** so được — và đó cũng là lý do
   mọi metric trong harness này đều dựa trên thứ hạng, không dựa trên điểm.
3. Năm biến thể của `bm25s` (`lucene`, `robertson`, `atire`, `bm25l`, `bm25+`) khác nhau ở
   đúng loại chi tiết này.

**Đã xử lý.** Cell đối chiếu trong `notebooks/02_lexical_search.ipynb` assert **hai** điều:
thứ hạng trùng khớp tuyệt đối, và điểm trùng khớp sau khi chia `(k1+1)`. Nó giữ vai trò
canary — nếu `bm25s` đổi công thức ở bản sau, notebook sẽ fail.

---

## F-008
### `bm25s` trả về kết quả điểm 0 và raise khi k > corpus

**Loại:** Library / silent zero-score results · **Tuần:** T2 · **Trạng thái:** ✅ đã sửa

**Hiện tượng.** Hai hành vi của thư viện mà adapter phải sửa:

1. Query không khớp token nào **vẫn** nhận về `k` văn bản tuỳ ý với `score = 0.0`. Không có
   lỗi, không có cảnh báo.
2. `k` lớn hơn số văn bản trong corpus thì `retrieve()` raise `ValueError`.

**Vì sao (1) nghiêm trọng.** Trên 61.425 văn bản, một kết quả "tuỳ ý" có xác suất nhỏ nhưng
khác 0 là chính văn bản đúng ⇒ **metric bị phồng bởi may mắn**. Tệ hơn về mặt trung thực:
report sẽ khai rằng BM25 "truy hồi được" 10 văn bản cho một câu mà nó chưa khớp một token
nào. Với một hệ thống mà cả mục đích là *đo cho đúng*, đó là lỗi nghiêm trọng hơn cả sai số.

**Vì sao (2) xuất hiện.** Adapter over-fetch `k × 3` trước khi gộp passage về document, nên
corpus nhỏ (4 văn bản trong test) kích hoạt ngay.

**Đã sửa** trong `src/retrieve/bm25.py`: lọc bỏ mọi hit `score <= 0`, và clamp `k` theo kích
thước corpus. Test chặn: `test_zero_score_padding_is_dropped`,
`test_k_larger_than_corpus_is_clamped_not_raised`.

**Nguyên tắc rút ra.** Khi bọc một thư viện retrieval, luôn hỏi: "nó trả gì khi không tìm
thấy gì?" Câu trả lời "một danh sách trông rất bình thường" là câu trả lời tệ nhất.

---

## F-009
### Chỉ số tổng hợp che mất một nửa sự thật

**Loại:** Method / aggregate hides churn · **Tuần:** T2 · **Trạng thái:** ✅ đã sửa

**Hiện tượng.** Đổi tokenizer `regex → underthesea` cho **MRR@10 +0,0108** — nhìn như một
thắng lợi gọn gàng. Nhưng so từng câu trên đúng 788 câu test đó:

| | số câu |
|---|---|
| tốt hơn | 183 |
| **tệ hơn** | **148** |
| không đổi | 457 |

**331 câu dịch chuyển, 45% đi lùi.** Con số công bố chỉ là *hiệu số* của hai nhóm ngược
chiều.

**Vì sao nghiêm trọng.** Kết luận rút ra từ metric tổng hợp — "underthesea tốt hơn, chốt" —
**sai về bản chất**. Sự thật là một cuộc đánh đổi: segmentation là quyết định cứng, một khi
`đường_cao_tốc` thành một token thì truy vấn được CRF cắt khác đi sẽ không khớp *gì cả*,
trong khi tokenizer âm tiết luôn khớp một phần. Nó đổi recall-một-phần lấy precision-toàn-phần.

Nếu không thấy 148 câu kia, ta sẽ không bao giờ hỏi "tại sao lại có câu tệ đi?", và sẽ bỏ
lỡ chính lý do hybrid retrieval (T4) tồn tại.

**Đã sửa.** Report giờ lưu `per_query` (ranking, điểm, metric, latency mỗi câu).
`src/eval/compare.py` phân nhóm improved/regressed/unchanged theo reciprocal rank và liệt kê
câu dịch chuyển mạnh nhất mỗi chiều. Dashboard hiển thị biểu đồ churn ngay cạnh delta, kèm
câu giải thích rằng delta là hiệu số. Test chặn:
`test_aggregate_can_hide_equal_and_opposite_churn`.

**Nguyên tắc rút ra.** Một thay đổi không bao giờ chỉ có một con số. Luôn hỏi "bao nhiêu câu
tệ đi?" trước khi nhận một mức lift.

---

## F-010
### Nút thắt thật: đúng văn bản, sai Điều

**Loại:** Retrieval / article resolution · **Tuần:** T2 · **Trạng thái:** 🔴 **nút thắt chính**

**Hiện tượng.** Phân loại 142 câu miss ở k=10 (BM25 `regex`, toàn corpus, 788 câu test) theo
số hiệu văn bản (phần trước dấu `+` trong corpus id):

| | số câu | % số miss |
|---|---|---|
| **đúng văn bản, sai Điều** | **93** | **65%** |
| sai hẳn văn bản | 49 | 35% |

Ví dụ, chú ý phần trước dấu `+` giống nhau:

```
cần 03/2013/tt-ttcp+5       nhận 03/2013/tt-ttcp+2, …
cần 100/2019/nđ-cp+15       nhận 100/2019/nđ-cp+47, …
cần 58/2010/qh12+3          nhận 58/2010/qh12+28, …
```

Thấy trực tiếp trong notebook: truy vấn "quay đầu xe cao tốc" trả về `100/2019/nđ-cp+5`
(đúng) rồi `+7`, `+6`, `+8` — cùng một Nghị định, các Điều xử phạt cho từng loại xe.

**Trần Recall@10 nếu chọn Điều hoàn hảo: 93,8%** (regex) / **95,4%** (underthesea), so với
86,1% hiện tại.

**Vì sao đây là failure mode quan trọng nhất.** Nó định lại hướng của toàn dự án. ~9 điểm
recall còn thiếu **không** nằm ở bài toán "tìm đúng luật" — mà ở "chọn đúng Điều trong luật".
Hai bài toán này cần công cụ khác nhau:

- Tìm văn bản: embedding tốt hơn, hybrid, metadata filter — **sẽ không giúp được gì đáng kể**
  vì văn bản đã tìm đúng rồi.
- Chọn Điều: cần tín hiệu ở mức nhỏ hơn Điều (chunking theo Khoản — T3) hoặc một model đọc
  kỹ nội dung để phân biệt (rerank — T4).

Các Điều trong cùng một Nghị định dùng gần như **cùng bộ từ vựng** ("phạt tiền", "người điều
khiển", "xe"), khác nhau ở chi tiết mà cả BM25 lẫn embedding cả-Điều đều làm mờ.

**Chưa xử lý.** Đây là nội dung chính của T3/T4. Cần bổ sung ngay một metric hạng nhất:
*tỷ lệ miss mà `doc_key` đúng nhưng `article_index` sai* — để mọi tuần sau đo được tiến bộ
trên đúng chiều này.

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
