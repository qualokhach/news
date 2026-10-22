# Chính sách nguồn tin và bản quyền — AppNho News MVP

## Trạng thái hiện tại
**Không có nguồn nào được phê duyệt để tự động xuất bản nội dung công khai.** Các nguồn trong `config/feeds.json` đều `enabled: false`. Workflow chỉ tạo danh sách gợi ý trong `data/pending.json`; nó không tự thêm tin vào `data/articles.json`.

## Nguyên tắc
1. RSS là phương tiện phát hiện nội dung, không tự động cấp quyền tái xuất bản.
2. Không sao chép RSS description, đoạn bài, ảnh, video, infographic hoặc nội dung toàn văn lên website nếu chưa có quyền rõ ràng.
3. Giữ URL nguồn, tên nhà xuất bản và thời gian lấy tin trong hàng chờ để biên tập viên mở nguồn gốc và tự xác minh.
4. Dữ kiện đơn lẻ có thể không được bảo hộ giống cách diễn đạt sáng tạo, nhưng việc thu thập, sử dụng cơ sở dữ liệu, điều khoản website, quyền liên quan và luật áp dụng vẫn cần được xem xét.
5. Chỉ bật một nguồn sau khi ghi rõ URL điều khoản, phạm vi dùng thương mại, phần nội dung được phép dùng, yêu cầu ghi công, giới hạn sửa đổi và ngày kiểm tra.
6. Nếu không xác minh được quyền, không bật nguồn. Dẫn link đến bài gốc thay vì sao chép nội dung.
7. Bản tin xuất bản phải được viết độc lập từ dữ kiện đã xác minh, có giá trị thông tin riêng và dẫn nguồn. Không dùng công cụ tự động để “đổi chữ” bài báo.
8. Chỉ dùng hình tự tạo hoặc hình có giấy phép rõ ràng cho đúng mục đích. Kiểm tra từng ảnh, không suy diễn rằng mọi ảnh trong một website đều dùng được.
9. Trước khi bật quảng cáo, cần đánh giá thêm chất lượng biên tập, quyền nội dung, chính sách quảng cáo và thông tin nhà xuất bản.

## Quy trình phê duyệt nguồn
- Kiểm tra trang điều khoản chính thức, không chỉ blog bên thứ ba.
- Xác định nội dung cụ thể được cấp phép: dữ kiện, tiêu đề, mô tả RSS, toàn văn, hình ảnh hay dữ liệu.
- Xác định quyền sử dụng thương mại và quyền dịch/chỉnh sửa.
- Lưu bằng chứng và ngày kiểm tra vào hồ sơ nguồn.
- Mặc định `enabled: false` cho đến khi hoàn tất.

## Hạn chế
Tài liệu này là hướng dẫn vận hành thận trọng, không phải ý kiến pháp lý và không bảo đảm miễn trừ mọi tranh chấp. Quyền sử dụng có thể khác theo quốc gia, loại tác phẩm, hợp đồng và thay đổi điều khoản.
