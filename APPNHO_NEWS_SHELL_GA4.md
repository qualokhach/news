# Header/footer AppNho + GA4 cho AppNho News

## Header / footer dùng chung với AppNho
- Cả 4 trang (index, article, about, admin) có header và footer giống appnho.io.vn. Mục "TIN TỨC" được đánh dấu đang xem.
- CSS lấy trực tiếp từ https://appnho.io.vn/assets/appnho-shell.css nên khi AppNho đổi giao diện, News tự theo.
- assets/appnho-news-bridge.css: ghi đè luật cũ trong style.css đang ẩn .site-header.
- Khi MENU hoặc FOOTER của AppNho đổi nội dung (thêm link...), chạy: python scripts/sync_appnho_shell.py
  (hoặc truyền đường dẫn file index.html trang chủ AppNho). Script chỉ thay phần nằm giữa các dòng APPNHO-SHELL:...:START/END.
- Footer có thêm 2 liên kết riêng của News: Nguyên tắc biên tập, RSS.

## GA4 (G-K9C4KKZPEE)
- Thẻ gtag nằm trong <head> của mọi trang HTML.
- Bài viết (kể cả bài tự động đăng sau này) đều mở qua article.html?id=<id> nên được ghi tự động, không cần làm gì thêm.
- assets/appnho-analytics.js: gửi page_view sau khi trang đã đặt tiêu đề (để GA4 hiện đúng tên từng bài); có đồng hồ dự phòng 6 giây.
- scripts/audit_site.py kiểm tra mọi *.html phải có GA4 + header/footer chung; thêm trang mới mà thiếu thì audit báo lỗi.
