# R8 Audit Report

## Kết quả
R8 được xây dựng từ gói R7 đầy đủ. Thay đổi tập trung vào điều hướng chuyên mục và cách chọn dữ liệu hiển thị. Dữ liệu gốc được giữ nguyên.

## Đếm dữ liệu
| Tập dữ liệu | Số bản ghi |
|---|---:|
| Bài đang hoạt động | 3 |
| Bài lưu trữ đầy đủ | 43 |
| Catalog lưu trữ | 43 |
| Pending (chờ biên tập/kiểm tra) | 122 |

Phân bố 43 bài lưu trữ theo chuyên mục: Việt Nam 31, Công nghệ 7, Thể thao 3, Thế giới 2.

## Các kiểm tra đã chạy
- Mọi tệp JSON trong gói phân tích đều parse thành công.
- `node --check assets/app.js`: đạt.
- `node --check assets/article.js`: đạt.
- `python scripts/test_pipeline_logic.py`: 7 kiểm thử đạt.
- Không có ID trùng giữa tập 3 bài đang hoạt động và tập 43 bài lưu trữ.
- ZIP được tạo sau khi loại bỏ cache Python.

## Phạm vi thay đổi chính
- `index.html`: thẻ chuyên mục điều hướng đến chế độ chuyên mục bằng query parameter.
- `article.html`: liên kết chuyên mục chuyển đến chế độ chuyên mục.
- `assets/app.js`: hợp nhất dữ liệu theo ID, hiển thị bài lưu trữ ở chuyên mục phù hợp, chế độ danh mục độc lập và nút tải thêm.
- `assets/style.css`: phong cách cho chế độ danh mục và nút tải thêm.

## Chưa xác minh
- Workflow lấy tin trực tiếp, phản hồi từ các API bên ngoài và website live sau deploy.
- Tương tác trình duyệt end-to-end chưa chạy trong môi trường này.
- 122 mục pending không phải bài đã xuất bản; không được đưa tự động lên trang công khai.
