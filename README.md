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
- Bài viết có ảnh thumbnail và ảnh minh họa trong nội dung từ Unsplash CDN; ảnh chỉ mang tính minh họa, không khẳng định là ảnh trực tiếp của sự kiện. Nếu ảnh không tải được do mạng/CDN, cần thay URL bằng ảnh đã kiểm tra trước khi xuất bản.
- Trang chủ hiện có ba bài mẫu biên tập độc lập dựa trên thông tin được đăng trên các trang chính thức của NASA và Cổng Thông tin điện tử Chính phủ Việt Nam. Đây là nội dung cụ thể có nguồn dẫn, không phải thông báo thử nghiệm. Trước khi xuất bản thương mại, vẫn cần rà soát lại từng dữ kiện, quyền sử dụng và điều khoản nguồn.
- Trước khi bật quảng cáo, cần rà soát chất lượng nội dung và các chính sách áp dụng.


## Nội dung mẫu trong bản cập nhật 22/10/2026

- `data/articles.json` có 40 bài: 30 bài thuộc kỳ tin từ 22/09 đến 22/10/2026 và 10 bài nhìn lại sự kiện tháng 10/2025. Mỗi bài có phần nội dung khoảng 650 từ trở lên; độ dài có thể tiếp tục điều chỉnh sau khi biên tập dữ kiện.
- Ngày hiển thị lấy từ `published_at`, không tự đổi sang ngày người dùng mở trang.
- Trường SEO mỗi bài gồm `seo_title`, `meta_description`, `keywords`, `slug`, `image_thumbnail`, `image_alt` và `images`. Trang chi tiết tạo meta description, keywords, Open Graph, Twitter Card và JSON-LD NewsArticle từ dữ liệu bài.
- Chuyên mục **Nhìn lại** được hiển thị riêng để tránh trình bày tin năm 2025 như tin nóng hiện tại.
- Workflow vẫn chỉ thu thập đầu mối RSS vào `data/pending.json`; không tự động xuất bản các đầu mối đó.
- Một số nguồn chính thức chỉ cung cấp trang danh mục trong trường hợp đường dẫn bài riêng không được xác minh trong lần biên tập này. Hãy mở nguồn trước khi trích dẫn hoặc dùng lại nội dung.


## Category thumbnails

News cards use four shared Cloudinary thumbnails based on article category: world, Vietnam, sports, and technology. The thumbnail URL is set in `data/articles.json`; article body illustrations remain in `assets/generated/`.


## Article images

Article pages no longer insert category thumbnails or generated SVG artwork into the body. Each of the current 43 articles has a contextual illustrative image URL hosted by Unsplash; captions identify these as illustrative rather than direct event photographs. Category thumbnails remain reserved for listing cards and social preview metadata. The homepage no longer includes the bottom “Đọc tin, hiểu bối cảnh” panel.
