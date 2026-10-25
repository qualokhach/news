# Thiết lập tự động đăng tin — GitHub-only

1. Trong `qualokhach/news`, vào Settings → Secrets and variables → Actions.
2. Thêm các khóa provider mà bạn đã tạo: `GEMINI_API_KEY_APPNHO_NEWS`, `GROK_API_APPNHO_NEWS`, `OPENROUTER_API_APPNHO_NEWS`. Không commit khóa vào repo.
3. Vào Actions → `AppNho News — collect, write and publish` → Run workflow.
4. Xem log: nếu không có khóa hoặc nguồn không đủ bằng chứng, hệ thống không xuất bản bài. Tối đa 4 bài mỗi lần chạy.
5. Nếu workflow thành công, kiểm tra commit mới cập nhật `data/articles.json`, `data/pending.json`, `data/seen_items.json`; historical `data/archive_articles.json` remains unchanged, `feed.xml`, `sitemap.xml`.
6. Kiểm tra trang chủ và mở một bài bằng URL `article.html?id=<id>`.

Lịch dự kiến: 06:00 và 17:00 giờ Việt Nam. Cron dùng UTC và GitHub có thể chạy trễ. Workflow cần quyền `contents: write` để commit dữ liệu. Không cần Cloudflare Worker, R2, D1 hoặc token quản trị.

Các model miễn phí và hạn mức API có thể thay đổi. Workflow cố gắng dùng provider tiếp theo khi có lỗi/quota, nhưng không bảo đảm đủ 8 bài/ngày.


GitHub Repository Secrets names used by this setup: `GEMINI_API_KEY_APPNHO_NEWS`, `GROK_API_APPNHO_NEWS`, and `OPENROUTER_API_APPNHO_NEWS`. The workflow maps these to runtime environment variables `GEMINI_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY` respectively.
