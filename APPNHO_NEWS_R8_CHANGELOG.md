# AppNho News R8 — changelog

## Mục tiêu
Sửa luồng điều hướng chuyên mục và thống nhất cách hiển thị bài đang hoạt động với bài lưu trữ, dựa trên R7. Không xóa hoặc tái tạo dữ liệu bài viết.

## Thay đổi
- Các thẻ chuyên mục ở trang chủ mở chế độ chuyên mục bằng `?category=world|vietnam|sports|technology`, thay vì chỉ cuộn đến một phần trên trang chủ.
- Liên kết chuyên mục trong trang chi tiết bài viết cũng mở chế độ chuyên mục tương ứng.
- `assets/app.js` tải dữ liệu bài đang hoạt động và dữ liệu lưu trữ; hợp nhất theo ID để tránh trùng bài.
- Các khối chuyên mục trên trang chủ có thể hiển thị bài thuộc chuyên mục từ dữ liệu hiện có, kể cả khi chuyên mục chưa có bài đang hoạt động; bài lưu trữ được đánh dấu “Nhìn lại”.
- Trang chuyên mục hiển thị riêng danh sách đúng chuyên mục, sắp xếp theo ngày và có nút “Xem thêm bản tin” khi còn bài.
- Giữ nguyên quy trình phân biệt bài đang hoạt động và bài lưu trữ; không đưa `pending.json` lên trang công khai.
- Thêm CSS cho chế độ chuyên mục và nút tải thêm.

## Dữ liệu được giữ nguyên
- `data/articles.json`: 3 bài đang hoạt động.
- `data/archive_articles.json`: 43 bài lưu trữ.
- `data/archive_catalog.json`: 43 mục danh mục lưu trữ.
- `data/pending.json`: giữ nguyên danh sách chờ biên tập của R7.
- Không thay đổi GitHub Actions, cấu hình API hoặc tên GitHub Secrets.

## Kiểm thử cục bộ
- JSON: hợp lệ.
- JavaScript syntax check (`node --check`): `assets/app.js` và `assets/article.js` đạt.
- `scripts/test_pipeline_logic.py`: 7/7 kiểm thử đạt.
- Kiểm tra dữ liệu: 3 bài đang hoạt động + 43 bài lưu trữ; không trùng ID giữa hai tập; lưu trữ gồm world 2, sports 3, technology 7, vietnam 31.

## Giới hạn
Chưa thể xác nhận kết quả chạy trực tiếp trên GitHub Pages hoặc kiểm tra tương tác bằng trình duyệt thật trong môi trường đóng gói. Sau khi commit, cần kiểm tra bốn đường dẫn `?category=world`, `?category=vietnam`, `?category=sports`, `?category=technology` và mở thử một bài trong mỗi danh mục có bài.
