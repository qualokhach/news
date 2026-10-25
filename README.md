# AppNho News R5 — GitHub-only archive and AI auto-publishing

## Kiến trúc đã chốt
- GitHub repository `qualokhach/news` giữ website, toàn bộ bài viết, hàng chờ RSS, lịch sử chống trùng và workflow.
- Không dùng Cloudflare R2, Worker hoặc D1 cho News trong phiên bản này.
- Website đọc bài từ `data/archive_articles.json` (43 bài lịch sử cố định) và `data/articles.json` (chỉ bài mới). Đường dẫn bài giữ dạng `article.html?id=<id>`.
- GitHub Actions chạy tự động 2 lần/ngày theo giờ Việt Nam mục tiêu 06:00 và 17:00, tối đa 4 bài/lượt. Chất lượng và bằng chứng nguồn quan trọng hơn số lượng; không đủ bằng chứng thì không xuất bản.
- Mỗi lần chạy tự động cập nhật JSON, RSS, sitemap rồi commit thay đổi vào repo. Lịch sử Git cũng sẽ tăng theo thời gian.

## Cập nhật repo
1. Giải nén ZIP.
2. Sao lưu hoặc tải ZIP repo hiện tại trước khi thay thế.
3. Upload các file trong ZIP vào thư mục gốc `qualokhach/news`, cho phép ghi đè file trùng tên, nhưng không xóa file khác của dự án nếu chưa đối chiếu.
4. Sau khi tải lên, chạy workflow **AppNho News — test AI API keys** trong tab Actions trước. Workflow này kiểm tra Secrets/model miễn phí mà không sinh bài.
5. Nếu kiểm tra đạt, chạy **AppNho News — collect, write and publish** bằng Run workflow để kiểm thử sinh bài thực tế.
6. Chỉ sau khi kiểm tra bài, URL, RSS và sitemap mới commit/gộp lên `main` hoặc để lịch chạy tự động.

Không commit thẳng vào `main` trước khi các bước kiểm tra trên đạt.
7. Vào Settings → Actions → General, kiểm tra quyền ghi nội dung repository. Workflow dùng `permissions: contents: write`; không cần Personal Access Token.
8. Vào Settings → Secrets and variables → Actions, dùng đúng các Secret: `GEMINI_API_KEY_APPNHO_NEWS`, `GROK_API_APPNHO_NEWS`, `OPENROUTER_API_APPNHO_NEWS`. Không gửi khóa cho người khác.

## Đăng bài thủ công
Mở [workflow đăng bài thủ công](https://github.com/qualokhach/news/actions/workflows/manual-publish.yml), chọn Run workflow và nhập các trường. Bài phải có ít nhất 600 từ và 6 đoạn. Workflow tự tạo ID duy nhất, thêm bài vào `data/articles.json` mà không sửa file lịch sử `data/archive_articles.json`, tái tạo `feed.xml` và `sitemap.xml`, rồi commit.

## Dữ liệu và URL
- Kho bài lịch sử (đóng băng, không ghi đè): `data/archive_articles.json` (43 bài hiện có).
- Kho bài mới: `data/articles.json` (chỉ các bài mới được đăng sau khi chuyển đổi).
- Lợi ích: mỗi commit mới không tạo phiên bản mới của toàn bộ 43 bài lịch sử. Git vẫn lưu lịch sử các phiên bản của file bài mới và các file metadata thay đổi.
- Hàng chờ: `data/pending.json`.
- Chống trùng: `data/seen_items.json` (giới hạn 20.000 mục gần nhất).
- URL chi tiết: `https://appnho.io.vn/news/article.html?id=<id>`.
- RSS: `/news/feed.xml`.
- Sitemap: `/news/sitemap.xml`.

## Hạn chế và bảo vệ
- Không có kho dữ liệu ngoài GitHub; các bản cập nhật tạo lịch sử commit. Hãy theo dõi dung lượng repo và website xuất bản.
- Không lưu API key trong file, HTML hoặc JavaScript. Chỉ đặt trong GitHub Actions Secrets.
- Không đặt PAT/token GitHub trong website.
- Workflow không có quyền xóa repo hoặc sửa Settings; chỉ có quyền ghi nội dung repository cần để cập nhật bài.
- Bản này đã được kiểm thử cục bộ; chưa thể xác nhận API key thực tế, hạn mức tài khoản hay website production cho đến khi workflow kiểm thử chạy trong GitHub của bạn.

## Quyền nguồn và chất lượng
RSS chỉ dùng làm đầu mối. Nội dung bài phải được biên tập độc lập, kiểm chứng nguồn và không sao chép nội dung có bản quyền. Đọc `SOURCE_AND_COPYRIGHT_POLICY.md`.


## Archive policy (GitHub-only)
The initial 43 articles live in immutable `data/archive_articles.json`. New articles accumulate in `data/articles.json`; after the active batch reaches 30 days, `scripts/rotate_archive.py` closes it into a new immutable JSON file under `data/archive_batches/`. The metadata catalog and manifest update only at rotation time. See `GITHUB_ONLY_ARCHIVE_SPLIT.md`.


GitHub Repository Secrets names used by this setup: `GEMINI_API_KEY_APPNHO_NEWS`, `GROK_API_APPNHO_NEWS`, and `OPENROUTER_API_APPNHO_NEWS`. The workflow maps these to runtime environment variables `GEMINI_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY` respectively.

## R5 AI API preflight
Run Actions → `AppNho News — test AI API keys` → Run workflow. It checks authentication/model discovery only and does not generate an article. The automatic workflow uses only allowlisted Gemini free-tier candidates, Groq Free Plan model IDs, and OpenRouter models with `:free` and zero token pricing; if no eligible model is available it reports failure rather than selecting a paid model.
