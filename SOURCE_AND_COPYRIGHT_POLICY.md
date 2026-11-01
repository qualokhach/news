# Chính sách nguồn tin và bản quyền — AppNho News v1.5.3

## Cấu hình nguồn hiện tại

- `config/feeds.json` giữ 50 RSS feed từ bản đang vận hành trước đây. Pipeline chỉ lấy tiêu đề, URL và ngày công bố; không lưu description hoặc toàn văn RSS.
- `config/source_directory.csv` giữ 228 đầu mối để tìm nguồn chính thức, dữ liệu, nghiên cứu và nguồn đối chiếu. Đây là danh mục tham khảo, không phải giấy phép crawl hay tái sử dụng thương mại.
- `access_status`, `terms_status` và `commercial_use_status` vẫn để `UNVERIFIED` cho đến khi được kiểm tra. Không tự đánh dấu nguồn đã được cấp phép.

## Chế độ nghiên cứu

1. `APPROVED_RESEARCH`: chỉ dùng khi `access_status=RESEARCH_ALLOWED` và `terms_status=VERIFIED`.
2. `LIMITED_FACTUAL_REFERENCE`: chế độ nghiên cứu giới hạn cho trang HTTPS công khai khi workflow bật `NEWS_PUBLIC_FACTUAL_RESEARCH=1`, robots.txt cho phép và nguồn không bị đánh dấu `BLOCKED`. Pipeline lấy một lượng văn bản giới hạn để kiểm chứng dữ kiện trong bộ nhớ, không lưu lại toàn văn hoặc đoạn trích trong repository.
3. Bài được tạo từ chế độ giới hạn phải ghi `reuse_mode=FACTUAL_CITATION_ONLY`, tự viết độc lập và dẫn URL nguồn. Không được sao chép câu chữ, ảnh, video, infographic hoặc cấu trúc sáng tạo của publisher.
4. Nếu biết điều khoản hoặc chính sách truy cập cấm cách sử dụng dự kiến, phải đặt `terms_status=BLOCKED` hoặc `access_status=BLOCKED`. Pipeline sẽ không truy cập nguồn đó. Không vượt paywall, CAPTCHA, đăng nhập, HTTP 401/403 hoặc giới hạn truy cập.

`LIMITED_FACTUAL_REFERENCE` không có nghĩa điều khoản đã được xác minh hoặc nguồn cấp giấy phép thương mại. Đây là cách dùng dữ kiện công khai để nghiên cứu và dẫn nguồn, không phải quyền tái xuất bản nội dung nguồn. Người quản lý vẫn cần cập nhật trạng thái khi hoàn tất rà soát điều khoản.

## Nguyên tắc biên tập và bản quyền

- RSS chỉ phát hiện đề tài; headline không được xem là bằng chứng cho dữ kiện trọng yếu.
- Mỗi bài phải có ít nhất ba claim trong fact ledger, mỗi claim gắn URL, evidence snippet và locator.
- Các trang đăng lại cùng thông cáo hoặc cùng wire service phải gom theo `source_family`, không tính thành nguồn độc lập.
- R1 cần hai source family độc lập hoặc một nguồn gốc phù hợp; R2 cần nguồn chính thức hoặc ba source family; R3 bắt buộc có nguồn chính thức và không chứa lời khuyên hành động cá nhân.
- Không lưu toàn văn bài báo nguồn; không tái sử dụng ảnh publisher nếu không có license thương mại xác minh.
- Ảnh Wikimedia chỉ được chèn khi license nằm trong whitelist thương mại; CC BY-NC, CC BY-ND-NC, CC BY-ND và giấy phép không rõ bị loại.

## Xuất bản

Candidate chỉ được đưa vào `research_queue.json` khi đạt QA. Finalizer kiểm tra lại freshness, robots, khả năng truy cập URL, fact ledger, source family và originality trước khi cập nhật `articles.json`. Nếu không đủ chứng cứ, bài bị HOLD hoặc bỏ qua; không hạ chuẩn để lấp lịch.
