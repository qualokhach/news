# AppNho News — v1.5.3 automated research and publication

## 1. Luồng vận hành

Repository `qualokhach/news` giữ website, dữ liệu bài viết, hàng đợi nghiên cứu, lịch sử chống trùng và workflow. Dữ liệu vẫn lưu trên GitHub; không dùng Cloudflare R2, Worker hoặc D1.

Hệ thống có ba luồng tách biệt:

1. **Research:** `scripts/news_pipeline.py` đọc RSS để lấy headline, URL và ngày công bố; gom sự kiện; kiểm tra trang nguồn độc lập; lập fact ledger; tạo bài mới; chỉ đưa bài đạt QA vào `data/research_queue.json`. Research không ghi vào `data/articles.json`.
2. **Finalize & publish:** `scripts/publish_ready.py` chạy 15 phút trước giờ xuất bản. Nó kiểm tra lại freshness, trạng thái nguồn, robots, HTTP, fact ledger, source family và chất lượng. Chỉ candidate READY còn hạn mới được đưa vào `data/articles.json`.
3. **Legacy upgrade:** chỉ chạy thủ công, mặc định dry-run. Workflow này không có lịch và không tự sửa 120 bài hiện có.

## 2. Lịch tự động (giờ Việt Nam, UTC+7)

| Công việc | Giờ Việt Nam | Cron UTC |
|---|---|---|
| Research | 09:00, 14:00, 21:00, 03:00 | `0 2,7,14,20 * * *` |
| Finalize/publish | 05:45, 11:45, 16:45 | `45 22,4,9 * * *` |
| Mục tiêu hiển thị | 06:00, 12:00, 17:00 | Finalizer chạy trước 15 phút |
| Legacy upgrade | Chỉ chạy thủ công | `workflow_dispatch` |

Lượt 12:00 xuất bản tối đa 4 tin MỚI (nghiên cứu, viết và kiểm duyệt như mọi lượt) rồi tạo điểm tin từ các bài AppNho mới nhất; bài cũ chỉ bổ sung khi chưa đủ 6 bài gần đây. Chỉ tạo digest khi có ít nhất 6 bài AppNho đạt `quality_version=1.5` và `quality_status=PASS`; không đủ thì bỏ lượt, không lấy RSS lead chưa nghiên cứu để lấp số lượng.

Cron được kiểm tra theo UTC. GitHub Actions có thể trễ hoặc bỏ lịch khi hệ thống quá tải; vì vậy không thể bảo đảm một bài sẽ xuất hiện đúng từng phút. Pipeline vẫn tự chạy và chỉ xuất bản khi có candidate qua QA.

## 3. RSS, nguồn và bằng chứng

- Giữ nguyên 50 URL RSS từ repository cũ đã vận hành. Feed chạy `DISCOVERY_ONLY`, chỉ lấy headline, URL và ngày công bố; không dùng RSS description làm chứng cứ.
- `config/source_directory.csv` giữ 228 nguồn và có đủ cột `terms_status`. Trạng thái điều khoản/quyền thương mại chưa xác minh vẫn để `UNVERIFIED`, không giả định đã được cấp phép.
- `APPROVED_RESEARCH` chỉ dùng khi `access_status=RESEARCH_ALLOWED` và `terms_status=VERIFIED`.
- `LIMITED_FACTUAL_REFERENCE` cho phép nghiên cứu dữ kiện giới hạn trên trang HTTPS công khai khi robots.txt cho phép và nguồn không bị đánh dấu `BLOCKED`. Chỉ trích xuất văn bản giới hạn tạm thời để kiểm tra sự kiện; không lưu toàn văn, không sao chép biểu đạt, không sử dụng ảnh publisher. Đây không phải xác nhận điều khoản đã được rà soát hay giấy phép thương mại.
- Nguồn bị đánh dấu `BLOCKED`, robots cấm hoặc HTTP 401/403 sẽ bị loại. Không vượt paywall, CAPTCHA, đăng nhập hoặc cơ chế kiểm soát truy cập.
- Bài R1 cần ít nhất hai source family độc lập hoặc một nguồn gốc phù hợp; R2 cần nguồn chính thức hoặc hai source family độc lập (danh sách từ khóa R2 đã thu hẹp); R3 bắt buộc nguồn chính thức. Claim trọng yếu phải có URL, evidence snippet và locator.

## 4. AI providers

Thứ tự fallback: **Gemini → Grok/xAI → OpenRouter**.

- Gemini ưu tiên `gemini-3.5-flash-lite` và chỉ dùng model hiện có trong danh sách API, có `generateContent`.
- Grok được chọn từ danh mục model xAI đang trả về, có cost ceiling. Generation gọi Responses API `/v1/responses` với `store=false`, tối đa 3 lần gọi Grok mỗi lượt research mặc định.
- OpenRouter chỉ dùng model `:free` có giá input/output bằng 0; giới hạn 8 lần gọi mỗi lượt research để tránh vượt quota free.

GitHub Secrets cần giữ đúng tên:

- `GEMINI_API_KEY_APPNHO_NEWS`
- `GROK_API_APPNHO_NEWS` (xAI, không phải Groq)
- `OPENROUTER_API_KEY_APPNHO_NEWS`

Workflow Research ánh xạ các secret sang `GEMINI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`.

`test-ai-apis.yml` là workflow chạy thủ công. Nó kiểm tra model catalog và gửi một yêu cầu sinh rất ngắn tới từng provider đã cấu hình. Lượt probe Grok có thể phát sinh một khoản phí API nhỏ. Workflow Research theo lịch chỉ kiểm tra model catalog trước khi chạy; việc sinh bài thực tế được kiểm chứng trong chính pipeline.

## 5. GitHub Actions

- `research-news.yml`: research, chuẩn bị candidate, không xuất bản.
- `build-news.yml`: finalizer và xuất bản theo lịch.
- `test-ai-apis.yml`: kiểm tra API/model và live probe khi chạy thủ công.
- `validate-news.yml`: kiểm tra code và dữ liệu khi push/PR.
- `manual-publish.yml`: đưa đề tài vào research queue, không xuất bản trực tiếp.
- `legacy-upgrade.yml`: nâng cấp bài cũ khi người quản lý chủ động chạy; mặc định dry-run.

Push code lên `main` không tự chạy pipeline xuất bản.

## 6. Dữ liệu

- `data/articles.json`: bài hiện hành.
- `data/archive_articles.json`: kho archive.
- `data/archive_catalog.json`, `data/archive_manifest.json`, `data/archive_batches/`: chỉ mục và các lô archive.
- `data/pending.json`: RSS leads và trạng thái xử lý.
- `data/research_queue.json`: bản thảo đã nghiên cứu, chờ finalizer.
- `data/seen_items.json`: chống trùng, cursor theo feed và thống kê.
- `data/publish_log.json`: kết quả từng khung xuất bản.
- `config/source_directory.csv`: 228 đầu mối nguồn.

`published_at` giữ ngày sự kiện/ngày nguồn. `appnho_published_at` là ngày AppNho xuất bản. Không ghi đè hai mốc này lẫn nhau.

Kho hiện có 120 bài: 77 active và 43 archive. Patch v1.5.3 không thay đổi nội dung, ID, slug hoặc ngày xuất bản lịch sử của các bài này.

## 7. Kiểm tra trước khi commit

Chạy tại thư mục gốc repository:

```bash
python -m compileall -q scripts
python -m unittest discover -s scripts -p 'test_*.py' -v
python scripts/audit_site.py
python scripts/build_metadata.py
```

Sau khi push, chạy lần lượt `Validate code and content data`, `Test AI API keys` và `Research and prepare candidates` thủ công. Khi research queue có candidate READY, chạy finalizer thủ công để kiểm tra đường xuất bản trước khi chờ cron.

## 8. URL

- Bài viết: `https://appnho.io.vn/news/article.html?id=<id>`
- RSS: `/news/feed.xml`
- Sitemap: `/news/sitemap.xml`
- Chính sách biên tập: `/news/about.html`
