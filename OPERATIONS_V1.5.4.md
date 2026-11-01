# AppNho News v1.5.4 — Vận hành

## Lịch tự động (giờ Việt Nam, UTC+7)

### Research
| Giờ Việt Nam | Cron UTC |
|---|---|
| 09:00 | `0 2 * * *` |
| 14:00 | `0 7 * * *` |
| 21:00 | `0 14 * * *` |
| 03:00 | `0 20 * * *` |

Research chỉ phát hiện, kiểm chứng và chuẩn bị candidate. Nó không ghi trực tiếp vào `data/articles.json`.

### Finalize và publish
| Giờ Việt Nam | Cron UTC | Loại phiên |
|---|---|---|
| 05:45 | `45 22 * * *` | Bài thường |
| 11:45 | `45 4 * * *` | Digest |
| 16:45 | `45 9 * * *` | Bài thường |

Ba cron phải được giữ riêng. `scripts/resolve_publish_slot.py` đọc event thực tế của GitHub Actions:
- 05:45 → `regular`, tối đa 4 bài.
- 11:45 → `digest`, không xuất bản bài thường trong slot này.
- 16:45 → `regular`, tối đa 4 bài.

Không đổi thành một cron gộp vì GitHub gửi `github.event.schedule` đúng chuỗi cron đã kích hoạt.

## GitHub Secrets

Giữ đúng ba tên secret:
- `GEMINI_API_KEY_APPNHO_NEWS`
- `GROK_API_APPNHO_NEWS`
- `OPENROUTER_API_KEY_APPNHO_NEWS`

Trong workflow, chúng được ánh xạ lần lượt sang `GEMINI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`.

Thứ tự provider khi tạo nội dung:
1. Gemini
2. Grok/xAI (có giới hạn số lần gọi)
3. OpenRouter (chỉ model miễn phí, giới hạn 8 lần gọi mỗi lượt Research)

## Kiểm tra sau khi commit

1. Chạy workflow `AppNho News — test AI API keys` với `workflow_dispatch`. Workflow dùng `--live-probe`, gửi yêu cầu sinh văn bản rất ngắn. Grok có thể phát sinh chi phí nhỏ nếu được kiểm tra.
2. Chạy workflow `AppNho News — research and prepare candidates` thủ công.
3. Kiểm tra log:
   - `FEED_AUDIT_SUMMARY`
   - `PIPELINE HEALTH`
   - `SUMMARY: new_leads=... prepared=...`
   - `[READY]` nếu có candidate đạt QA.
4. Chạy `AppNho News — finalize and publish by schedule` thủ công với `slot_kind=regular` để kiểm tra xuất bản bài thường, hoặc `slot_kind=digest` để kiểm tra digest.
5. Khi hai workflow chạy đúng, để lịch tự động tiếp tục.

## Quy tắc an toàn

- RSS chỉ là discovery metadata; không dùng RSS lead làm chứng cứ cho claim.
- Nguồn bị robots chặn, trả lỗi, CAPTCHA hoặc paywall không được dùng làm chứng cứ.
- Dữ kiện phải có trích đoạn nguyên văn từ đúng URL.
- Claim cốt lõi cần một nguồn chính phù hợp hoặc hai source family độc lập.
- Trước publish, hệ thống tải lại các trang chứa chứng cứ và kiểm tra snippet còn tồn tại.
- Candidate không đạt sẽ HOLD/REJECT; không hạ chuẩn để lấp slot.
- Bài cũ không tự nâng cấp theo lịch; legacy upgrade chỉ chạy thủ công.

## Giới hạn xác nhận

Audit offline không thể kiểm tra GitHub Secrets hoặc xác nhận 50 RSS feed đang trả HTTP trong runner GitHub. Những bước này chỉ được xác nhận sau khi commit và chạy hai workflow kiểm tra thực tế. Bản v1.5.4 giữ nguyên URL feed và tên secret từ repository trước đó; không chứa API key.
