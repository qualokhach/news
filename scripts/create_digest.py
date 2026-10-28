#!/usr/bin/env python3
"""Create a compact, idempotent AppNho News noon digest from already published stories."""
import json, re, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / "data/articles.json"
ARCHIVE = ROOT / "data/archive_articles.json"
CATALOG = ROOT / "data/archive_catalog.json"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
LABELS = {"vietnam":"Việt Nam", "world":"Thế giới", "technology":"Công nghệ", "sports":"Thể thao"}

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(VN).date().isoformat()
    active = json.loads(ARTICLES.read_text(encoding="utf-8")) if ARTICLES.exists() else []
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.exists() else []
    catalog = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else []
    all_articles = archive + catalog + active
    digest_id = "diem-tin-" + today
    if any(a.get("id") == digest_id for a in all_articles):
        print(f"[DIGEST] Already exists for {today}; no duplicate created.")
        return
    cutoff = now - timedelta(hours=36)
    eligible = []
    seen_titles = set()
    seen_ids = set()
    for a in sorted(all_articles, key=lambda x: x.get("published_at", ""), reverse=True):
        if a.get("content_type") == "news_digest" or a.get("category") not in LABELS:
            continue
        article_id = str(a.get("id") or "")
        if article_id and article_id in seen_ids:
            continue
        try:
            dt = datetime.fromisoformat(str(a.get("published_at", "")).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
        except Exception:
            continue
        title = clean(a.get("title"))
        summary = clean(a.get("summary"))
        key = re.sub(r"[^a-z0-9]+", "", title.lower())
        if not title or not summary or not key or key in seen_titles:
            continue
        seen_titles.add(key)
        if article_id:
            seen_ids.add(article_id)
        eligible.append(a)

    if len(eligible) < 6:
        print(f"[DIGEST] Only {len(eligible)} eligible published stories; need at least 6. Skipping digest without failing the main publication workflow.")
        return

    # Balance categories across the full eligible pool, not just the newest ten.
    # First select one from each available category, then fill with the newest remaining stories.
    chosen, used = [], set()
    for category in ("vietnam", "world", "technology", "sports"):
        match = next((a for a in eligible if a.get("category") == category), None)
        if match:
            chosen.append(match)
            used.add(str(match.get("id") or match.get("title")))
    for a in eligible:
        if len(chosen) >= 10:
            break
        key = str(a.get("id") or a.get("title"))
        if key not in used:
            chosen.append(a)
            used.add(key)
    chosen = chosen[:10]
    date_vn = now.astimezone(VN).strftime("%d/%m/%Y")
    title = f"Điểm tin AppNho trưa {date_vn}: {len(chosen)} tin đáng chú ý"
    summary = "Tổng hợp ngắn các diễn biến đáng chú ý tại Việt Nam và thế giới, cùng tin công nghệ và thể thao. Mỗi mục tóm lược ý chính và dẫn về bài nguồn để bạn đọc thêm."
    body = [f"Bản tin điểm tin trưa {date_vn} tổng hợp {len(chosen)} tin từ các bài đã được AppNho News xuất bản gần đây. Các tin được rút gọn để nắm nhanh diễn biến; mở liên kết nguồn để xem thông tin đầy đủ."] + body + ["Lưu ý: Đây là bản tóm tắt các bài đã xuất bản, không thay thế nội dung chi tiết hoặc cập nhật mới nhất từ nguồn tin."]
    ident = digest_id
    article = {
      "id": ident, "title": title, "summary": summary, "category": "vietnam",
      "source_name": "AppNho News — tổng hợp", "source_url": "https://appnho.io.vn/news/",
      "published_at": now.isoformat(), "fetched_at": now.isoformat(),
      "content_type": "news_digest", "collection": "current", "body": body,
      "editorial_note": "Bản tin tổng hợp tự động từ các bài AppNho News đã xuất bản; các mục có thể trùng với bài riêng.",
      "generation_provider": "deterministic_digest", "seo_title": title[:70],
      "meta_description": summary[:160], "keywords": ["điểm tin", "tin Việt Nam", "tin thế giới", "tin công nghệ", "tin thể thao"],
      "slug": ident, "images": [], "content_image_url": "", "content_image_alt": "",
      "content_image_credit": "", "content_image_credit_url": "", "word_count": len(" ".join(body).split()),
      "display_source": True, "source_urls": list(dict.fromkeys(u for u in links if u)),
      "source_links": list(dict.fromkeys(u for u in links if u))
    }
    active.append(article)
    ARTICLES.write_text(json.dumps(active, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[DIGEST] Created {ident} with {len(chosen)} short items across categories: " + ", ".join(sorted({a.get('category','') for a in chosen})))

if __name__ == "__main__": main()
