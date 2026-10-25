# Bàn giao — chuyển AppNho News sang GitHub-only

## Quyết định
Không dùng R2/Worker/D1 cho News ở giai đoạn hiện tại. GitHub repo là kho dữ liệu chính. Đánh đổi: repo và lịch sử Git tăng theo mỗi lần cập nhật; đổi lại chưa cần đăng ký dịch vụ lưu trữ Cloudflare.

## Có trong gói
- 43 bài hiện có được giữ nguyên ID trong `data/archive_articles.json` bất biến; `data/articles.json` chỉ chứa bài mới phát sinh.
- Pipeline đọc cả kho lịch sử và kho bài mới để chống trùng; chỉ ghi bài mới vào `articles.json`, không ghi lại `archive_articles.json`.
- Workflow tự động có quyền `contents: write` và commit các file dữ liệu, RSS, sitemap khi có thay đổi.
- Workflow đăng bài thủ công dùng `workflow_dispatch`; không đặt token trong frontend.
- Sitemap và RSS được tái tạo sau khi xuất bản bài.

## Triển khai an toàn
1. Tải bản sao repo `qualokhach/news` trước khi ghi đè.
2. Upload các file từ ZIP vào root repo và đối chiếu thay đổi trước khi commit.
3. Xác nhận `data/archive_articles.json` vẫn có đủ 43 bài và ID cũ; bài mới được thêm riêng vào `data/articles.json`.
4. Kiểm tra GitHub Actions Secrets cho các AI provider. Không có khóa thì pipeline chỉ thu thập RSS, không viết bài.
5. Chạy workflow tự động thủ công trước; kiểm tra commit, homepage, trang chi tiết, RSS, sitemap.
6. Chạy workflow manual publish với bài thử chất lượng cao; kiểm tra URL `article.html?id=<id>`.
7. Chỉ sau khi test đạt mới để lịch tự động chạy.

## Các kiểm tra được thực hiện khi đóng gói
- Kiểm tra cú pháp Python và YAML.
- Kiểm tra JSON articles/pending/seen và bảo toàn ID bài cũ.
- Kiểm tra không còn tham chiếu runtime đến `NEWS_STORAGE_API_URL`, `NEWS_STORAGE_ADMIN_TOKEN` hoặc Worker API trong pipeline/frontend.

## Chưa được xác nhận
Chưa chạy GitHub Actions trên tài khoản thật, chưa xác minh Secrets, chưa deploy/kiểm tra Vercel hoặc tên miền production. Không tuyên bố hệ thống live cho đến khi các bước E2E hoàn tất.

## GitHub-only archive batches (R5)
- First immutable batch: `data/archive_articles.json` (43 articles through 22/10/2026).
- Current batch: `data/articles.json`.
- A scheduled/manual workflow invokes `scripts/rotate_archive.py`. Once the oldest active article reaches 30 days, the whole active batch is closed into `data/archive_batches/` and will not be overwritten.
- `archive_catalog.json` stores metadata and the batch path; the article page loads the specific archive file on demand.
- Backfilled daily briefings are included for 23–25/10/2026.

## R5 API preflight
A new manual workflow `test-ai-apis.yml` validates the three configured repository secrets and free-model discovery without generating content. Run it first. Then run the main pipeline manually and verify generated article content and deployment before enabling schedule.
