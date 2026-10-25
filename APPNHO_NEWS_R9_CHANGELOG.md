# AppNho News R9 — Full Commit Changelog

## Mục tiêu
R9 kế thừa toàn bộ dữ liệu và giao diện R8, đồng thời xử lý các điểm rủi ro được phát hiện khi audit workflow, lịch sử lưu trữ, RSS/sitemap và liên kết nội bộ. Không thay đổi tên GitHub Secrets.

## Thay đổi chính

### 1. Hiển thị đầy đủ kho lưu trữ
- `assets/app.js` và `assets/article.js` đọc `data/archive_manifest.json` và tải các archive batch được manifest/catalog tham chiếu.
- Hợp nhất bài theo ID, ưu tiên bản đầy đủ, tránh đưa catalog metadata thành bản sao bài viết.
- Bài lưu trữ mới sau lần xoay batch 30 ngày vẫn có thể xuất hiện ở chuyên mục và mở bằng URL bài viết.
- Lỗi tải một archive batch riêng lẻ được ghi cảnh báo, không làm mất toàn bộ giao diện nếu dữ liệu chính vẫn tải được.

### 2. Sửa luồng tự động và khả năng phát hiện lỗi
- Giữ lịch chạy tự động 06:00 và 17:00 giờ Việt Nam (cron UTC `0 23,10 * * *`).
- Workflow kiểm tra dữ liệu, chạy kiểm thử hồi quy, xác nhận có ít nhất một AI provider secret (không in giá trị secret), kiểm tra thống kê sau pipeline và audit lại dữ liệu.
- Bổ sung `scripts/check_run_health.py`; run thất bại rõ ràng nếu không có feed nào thành công, không có khóa AI, hoặc đã thử sinh bài nhưng không nhận được phản hồi AI hợp lệ.
- Bổ sung thống kê số lần thử sinh bài, phản hồi AI và lỗi sinh bài vào `data/seen_items.json`.
- Bỏ `[skip ci]` khỏi commit dữ liệu tự động để không chặn các workflow triển khai Pages bị kích hoạt bởi push. Pipeline không có trigger `push`, nên commit do bot không tự khởi chạy lại pipeline.

### 3. RSS, sitemap và SEO
- `scripts/build_metadata.py` loại trùng theo ID giữa bài lưu trữ, catalog và bài đang hoạt động.
- Canonical trang chủ chuyển sang URL GitHub Pages đúng với repo dự án: `https://qualokhach.github.io/news/`.
- RSS và sitemap được tái tạo sau pipeline/rotation.

### 4. Cơ chế audit
- Thêm `scripts/audit_site.py` để xác thực JSON, IDs, phân loại, archive manifest/catalog, sự hiện diện của đủ bốn chuyên mục, đường dẫn nội bộ và cấu hình lịch.
- Workflow chạy audit trước và sau khi sinh bài, và sau khi xoay archive.
- Chạy kiểm thử hồi quy hiện có của pipeline ở mỗi lần chạy tự động.

## Dữ liệu được bảo toàn
- `data/articles.json`: 3 bài đang hoạt động tại thời điểm đóng gói.
- `data/archive_articles.json`: 43 bài lưu trữ hiện có.
- `data/archive_catalog.json`: 43 mục catalog.
- `data/pending.json`: 122 mục chờ biên tập/kiểm tra; không tự đưa lên website.
- Không sửa nội dung bài hiện có và không đổi tên secrets.

## Giới hạn xác minh
- Đã kiểm thử cục bộ dữ liệu, mã JavaScript/Python, kiểm thử pipeline, liên kết nội bộ và mô phỏng xoay archive 30 ngày.
- Không thể xác nhận giá trị/hiệu lực thực tế của GitHub Secrets, phản hồi API trực tiếp, nguồn RSS trực tiếp hay hành vi live sau khi người dùng commit. Workflow R9 sẽ kiểm tra các điều kiện này và ghi log rõ hơn khi chạy trên GitHub.
