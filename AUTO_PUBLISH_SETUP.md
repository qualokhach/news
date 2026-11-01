# Thiết lập AppNho News v1.5

## GitHub Secrets
Trong Settings → Secrets and variables → Actions, giữ ba Secret:
- `GEMINI_API_KEY_APPNHO_NEWS`
- `GROK_API_APPNHO_NEWS`
- `OPENROUTER_API_APPNHO_NEWS`

`GROK_API_APPNHO_NEWS` được ánh xạ sang `XAI_API_KEY`. Đây là Grok/xAI, không phải Groq.

## Workflow
- `research-news.yml`: nghiên cứu và chuẩn bị ứng viên; không xuất bản.
- `build-news.yml`: chạy finalizer trước lịch 06:00, 12:00, 17:00 giờ Việt Nam.
- `legacy-upgrade.yml`: nâng cấp bài đã xuất bản theo lô, không yêu cầu duyệt từng bài.
- `validate-news.yml`: kiểm thử khi push/PR; không xuất bản.
- `test-ai-apis.yml`: kiểm tra API/model, không sinh bài.

## Giờ chạy
- Research: 09:00, 14:00, 21:00 và 03:00 giờ Việt Nam.
- Finalizer: 05:45, 11:45 và 16:45.
- Legacy upgrade: 12:30, 18:30, 00:30 và 06:30.
- Bản điểm tin được tạo trong lượt finalizer 11:45 và chỉ dùng bài AppNho đã xuất bản; bài cũ hơn phải có ngày sự kiện/nguồn rõ ràng.

## Cách triển khai
1. Sao lưu repo `qualokhach/news`.
2. Upload các file cập nhật trong ZIP vào đúng thư mục, ghi đè file trùng tên.
3. Chạy CI validation; kiểm tra `python -m unittest discover -s scripts -p 'test_*.py' -v` và `python scripts/audit_site.py`.
4. Kiểm tra Secrets. Không đặt API key trong file hoặc frontend.
5. Sau commit, theo dõi các workflow research, publish và legacy-upgrade trong Actions.

Push code không kích hoạt xuất bản ngoài lịch. Không cần kết nối GitHub từ ChatGPT; người dùng tự commit ZIP.

## Lưu ý
Danh mục nguồn là danh mục tìm kiếm, không phải giấy phép tự động crawl/tái sử dụng. Những nguồn chưa kiểm tra vẫn là chưa xác minh. Pipeline không vượt paywall, CAPTCHA, đăng nhập hoặc HTTP 401/403. Kiểm tra robots.txt không thay thế việc kiểm tra điều khoản nguồn.

Các bài cũ được nâng cấp theo lô. Script giữ nguyên ID, slug và ngày lịch sử; chỉ thay nội dung khi có chứng cứ mới và vượt qua QA v1.5. Nếu thiếu căn cứ, bài chuyển HOLD tự động và script chuyển sang bài khác. Không thể bảo đảm mọi bài đều nâng cấp thành công nếu nguồn gốc không còn truy cập được.
