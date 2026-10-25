# AppNho News R9 — Audit & Validation Report

## Kết quả kiểm tra cục bộ
- `scripts/audit_site.py`: PASS.
- Kiểm tra liên kết: PASS — 35 liên kết trong 4 trang HTML, không phát hiện đích nội bộ bị thiếu.
- JSON: tất cả JSON được đọc bởi audit hợp lệ.
- `node --check assets/app.js`: PASS.
- `node --check assets/article.js`: PASS.
- `python -m py_compile scripts/*.py`: PASS.
- `python -m unittest discover -s scripts -p 'test_*.py' -v`: 7/7 PASS.
- YAML parse cho các workflow: PASS.
- `scripts/build_metadata.py`: PASS; tạo sitemap 48 URL và RSS 46 bài, không nhân đôi 43 bài lưu trữ trong RSS.
- Mô phỏng xoay batch 30 ngày trên bản sao tạm: PASS; 3 bài đang hoạt động chuyển vào batch mới, manifest/catalog cập nhật, audit sau xoay đạt với 46 bài lưu trữ và 0 bài active. Bản dữ liệu đóng gói không bị thay đổi bởi phép thử này.
- ZIP: được kiểm tra sau khi đóng gói; xem SHA-256 bên dưới.

## Dữ liệu trong gói R9
| Tập dữ liệu | Số lượng |
|---|---:|
| Bài đang hoạt động | 3 |
| Bài lưu trữ đầy đủ | 43 |
| Catalog lưu trữ | 43 |
| Mục chờ biên tập/kiểm tra | 122 |
| Chuyên mục có bài | 4/4 |

## Phát hiện đã xử lý
1. Giao diện chỉ tải `archive_articles.json`, không tải các batch tương lai được liệt kê trong manifest.
2. RSS có nguy cơ lặp bài vì ghép archive và catalog như hai tập bài độc lập.
3. Commit bot dùng `[skip ci]`, có thể làm cản workflow triển khai do push kích hoạt.
4. Workflow không có bước audit dữ liệu/đường dẫn trước và sau khi chạy pipeline, và không báo lỗi rõ nếu tất cả feed hoặc mọi lần gọi AI thất bại.
5. Canonical trang chủ trỏ `/`, không phải đường dẫn dự án GitHub Pages `/news/`.

## Không tuyên bố đã xác minh
Không có quyền đọc giá trị secrets và không thực hiện được kiểm thử trình duyệt end-to-end trong môi trường đóng gói. Chưa xác nhận API providers/RSS nguồn ngoài hoặc website live. Các kiểm tra online sẽ diễn ra khi R9 chạy trên GitHub Actions; nếu điều kiện nền tảng không đạt, workflow sẽ báo đỏ kèm lý do thay vì âm thầm báo thành công.

## Gói bàn giao
- File: `APPNHO_NEWS_R9_FULL_COMMIT.zip`
- Số tệp trong ZIP: 137
- Kết quả kiểm tra ZIP: hợp lệ (`testzip` không báo lỗi)
- SHA-256: xem mã băm trong thông tin bàn giao đi kèm ZIP.
- Bốn tệp dữ liệu cốt lõi `articles.json`, `archive_articles.json`, `archive_catalog.json`, `pending.json` được so sánh byte-for-byte với R8: không thay đổi.
