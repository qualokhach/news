# AppNho News — bản MVP thận trọng về bản quyền

Website tĩnh và bộ thu thập metadata RSS chạy trên GitHub Actions. Không cần máy tính cá nhân chạy nền và không gọi API AI trả phí.

## Điểm khác biệt quan trọng
Bản này **không tự động xuất bản bài RSS ra website**. Các nguồn đều tắt mặc định. Workflow chỉ thu thập tiêu đề, URL, tên nguồn, danh mục và ngày đăng vào `data/pending.json` để người biên tập kiểm tra. Nó không lưu mô tả RSS hay toàn văn bài nguồn. `data/articles.json` là dữ liệu công khai của website và chỉ nên chứa bài do bạn tự viết/biên tập sau khi xác minh quyền, dữ kiện và nguồn.

RSS không mặc nhiên cấp quyền tái xuất bản. Xem `SOURCE_AND_COPYRIGHT_POLICY.md` trước khi bật nguồn hoặc xuất bản.

## 1. Đưa mã lên GitHub
1. Giải nén ZIP.
2. Mở `https://github.com/qualokhach/news`.
3. Chọn **Add file → Upload files**, tải toàn bộ nội dung trong thư mục `appnho-news` lên thư mục gốc repo.
4. Commit lên nhánh `main`.

## 2. Chạy thử
Vào **Actions → Build news from RSS → Run workflow**. Với cấu hình mặc định, không có nguồn nào được bật, nên workflow sẽ không thu thập nội dung. Đây là lựa chọn an toàn mặc định.
Sau khi kiểm tra điều khoản một nguồn cụ thể, bạn có thể bật `enabled: true` trong `config/feeds.json`. Workflow khi đó chỉ thêm metadata vào hàng chờ `data/pending.json`, không xuất bản lên trang chủ.

Lịch mặc định: 00:00 và 10:00 UTC, tương ứng 07:00 và 17:00 giờ Việt Nam. GitHub Actions có thể chạy trễ.

## 3. Triển khai Vercel
Import repository `qualokhach/news` vào Vercel, preset **Other**, build command để trống, output directory `.`.

## 4. Quy trình biên tập
1. Xem các mục trong `data/pending.json`, mở link nguồn gốc.
2. Kiểm tra sự kiện, dữ kiện, ngày tháng và quyền sử dụng.
3. Viết bản tin độc lập từ thông tin đã xác minh, không sao chép/đổi chữ bài gốc.
4. Chỉ thêm vào `data/articles.json` sau khi có nội dung tự viết và nguồn được phép dẫn/ sử dụng. Ghi link nguồn rõ ràng.
5. Nếu không rõ quyền dùng nội dung, chỉ dẫn link tới nguồn gốc và không tái xuất bản văn bản/ảnh của nguồn.

## 5. Lưu ý
- Không có AI tạo bài trong bản MVP này; không gọi API AI trả phí.
- Hình minh họa giao diện được vẽ bằng CSS, không dùng ảnh báo chí.
- Bản tin công khai mẫu là thông báo thiết lập của chính AppNho News, không phải tin lấy từ bên thứ ba.
- Trước khi bật quảng cáo, cần rà soát chất lượng nội dung và các chính sách áp dụng.
