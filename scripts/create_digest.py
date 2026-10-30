#!/usr/bin/env python3
"""Create the AppNho noon digest: prioritize stories published in the last 24h.

If fewer than six fresh published AppNho stories are available, supplement only
as many as needed from older already-published AppNho stories. Never use raw RSS
leads/pending items as digest content.
"""
import json
import re
import hashlib
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / "data/articles.json"
ARCHIVE = ROOT / "data/archive_articles.json"
CATALOG = ROOT / "data/archive_catalog.json"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
LABELS = {"vietnam": "Việt Nam", "world": "Thế giới", "technology": "Công nghệ", "sports": "Thể thao"}
BASE_URL = "https://www.appnho.io.vn/news/article.html?id="
MIN_ITEMS = 6
MAX_ITEMS = 10
FRESH_HOURS = 24


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_json(path):
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        print(f"[DIGEST][WARN] Could not read {path.name}; treating it as empty.")
        return []


def parse_datetime(value):
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def story_text(article):
    """Use the AppNho-edited summary/body, never copy raw RSS descriptions."""
    summary = clean(article.get("summary"))
    if summary:
        return summary
    body = article.get("body")
    if isinstance(body, list):
        return clean(" ".join(clean(x) for x in body[:2] if clean(x)))
    return clean(body)


def collect_published(active, archive, catalog, now):
    # Full article records take precedence over catalog-only metadata.
    by_id = {}
    for article in active + archive + catalog:
        if not isinstance(article, dict):
            continue
        ident = clean(article.get("id"))
        if not ident:
            continue
        if ident not in by_id or (not by_id[ident].get("body") and article.get("body")):
            by_id[ident] = article

    rows = []
    seen_titles, seen_urls = set(), set()
    for article in by_id.values():
        if article.get("content_type") == "news_digest" or article.get("category") not in LABELS:
            continue
        title = clean(article.get("title"))
        summary = story_text(article)
        ident = clean(article.get("id"))
        published = parse_datetime(article.get("published_at"))
        if not title or not summary or not ident or not published or published > now:
            continue
        title_key = re.sub(r"[^a-z0-9\u00c0-\u024f]+", "", title.casefold())
        url_key = clean(article.get("source_url"))
        if title_key and title_key in seen_titles:
            continue
        if url_key and url_key in seen_urls:
            continue
        if title_key:
            seen_titles.add(title_key)
        if url_key:
            seen_urls.add(url_key)
        rows.append({
            "id": ident,
            "title": title,
            "summary": summary,
            "category": article.get("category"),
            "published_at": published.isoformat(),
            "source_name": clean(article.get("source_name")) or "AppNho News",
            "source_url": clean(article.get("source_url")),
            "appnho_url": BASE_URL + quote(ident, safe=""),
            "image": clean(article.get("content_image_url") or article.get("image_thumbnail")),
        })
    return sorted(rows, key=lambda x: x["published_at"], reverse=True)


def choose_items(rows, now):
    cutoff = now - timedelta(hours=FRESH_HOURS)
    fresh = [x for x in rows if parse_datetime(x["published_at"]) >= cutoff]
    older = [x for x in rows if parse_datetime(x["published_at"]) < cutoff]
    chosen = fresh[:MAX_ITEMS]
    supplement_count = 0
    if len(chosen) < MIN_ITEMS:
        needed = MIN_ITEMS - len(chosen)
        additions = older[:needed]
        chosen.extend(additions)
        supplement_count = len(additions)
    return chosen[:MAX_ITEMS], len(fresh), supplement_count


def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(VN).date().isoformat()
    active = load_json(ARTICLES)
    archive = load_json(ARCHIVE)
    catalog = load_json(CATALOG)
    digest_id = "diem-tin-" + today
    all_records = active + archive + catalog
    existing_today = any(isinstance(a, dict) and a.get("id") == digest_id for a in all_records)
    rebuild = os.environ.get("REBUILD_DIGEST", "").strip().lower() in {"1", "true", "yes"}
    if existing_today and not rebuild:
        print(f"[DIGEST] Already exists for {today}; no duplicate created. Set REBUILD_DIGEST=1 to replace today's digest.")
        return
    if existing_today and rebuild:
        # Only replace today's digest in the active article list. Never rewrite or delete archive files.
        active = [a for a in active if not (isinstance(a, dict) and a.get("id") == digest_id)]
        archive = [a for a in archive if not (isinstance(a, dict) and a.get("id") == digest_id)]
        catalog = [a for a in catalog if not (isinstance(a, dict) and a.get("id") == digest_id)]
        print(f"[DIGEST] Rebuilding today's digest {digest_id}; source articles and archives remain unchanged.")

    rows = collect_published(active, archive, catalog, now)
    chosen, fresh_count, supplement_count = choose_items(rows, now)
    print(f"[DIGEST] Fresh published stories in last {FRESH_HOURS}h: {fresh_count}")
    print(f"[DIGEST] Older published stories used as supplement: {supplement_count}")
    if len(chosen) < MIN_ITEMS:
        print(f"[DIGEST] Only {len(chosen)} eligible published stories available; need at least {MIN_ITEMS}. No digest published.")
        return

    date_vn = now.astimezone(VN).strftime("%d/%m/%Y")
    title = f"Điểm tin AppNho trưa {date_vn}: {len(chosen)} tin đáng chú ý"
    summary = (f"{len(chosen)} tin đáng chú ý từ các chuyên mục Việt Nam, Thế giới, Công nghệ và Thể thao. "
               "Ưu tiên tin mới trong 24 giờ; chỉ bổ sung bài đã xuất bản trước đó khi tin mới chưa đủ sáu.")
    digest_items = []
    source_urls = []
    for index, item in enumerate(chosen, 1):
        digest_items.append({
            "number": index,
            "title": item["title"],
            "category": LABELS.get(item["category"], "Tin tức"),
            "summary": item["summary"],
            "url": item["appnho_url"],
            "published_at": item["published_at"],
            "is_supplement": parse_datetime(item["published_at"]) < now - timedelta(hours=FRESH_HOURS),
        })
        if item["source_url"]:
            source_urls.append(item["source_url"])

    body = [
        f"Bản tin điểm tin trưa {date_vn} gồm {len(chosen)} tin. Hệ thống ưu tiên các bài AppNho News mới xuất bản trong 24 giờ gần nhất. "
        + (f"Do số tin mới chưa đủ sáu, đã bổ sung {supplement_count} bài AppNho News xuất bản trước đó." if supplement_count else "Tất cả mục dưới đây được chọn từ nhóm tin mới trong 24 giờ.")
    ]
    body.extend(f"{x['number']}. {x['title']} — {x['summary']}" for x in digest_items)
    body.append("Mỗi mục có liên kết đến bài viết chi tiết trên AppNho News.")
    ident = digest_id
    article = {
        "id": ident, "title": title, "summary": summary, "category": "vietnam",
        "source_name": "AppNho News — tổng hợp", "source_url": "https://appnho.io.vn/news/",
        "published_at": now.isoformat(), "fetched_at": now.isoformat(),
        "content_type": "news_digest", "collection": "current", "body": body,
        "digest_items": digest_items,
        "digest_window_hours": FRESH_HOURS,
        "digest_fresh_count": fresh_count,
        "digest_supplement_count": supplement_count,
        "editorial_note": "Ưu tiên tin mới trong 24 giờ từ các bài AppNho News đã biên tập và xuất bản; chỉ dùng bài xuất bản cũ để bù khi thiếu sáu tin mới.",
        "generation_provider": "deterministic_digest", "seo_title": title[:70],
        "meta_description": summary[:160], "keywords": ["điểm tin", "tin Việt Nam", "tin thế giới", "tin công nghệ", "tin thể thao"],
        "slug": ident, "images": [], "content_image_url": "", "content_image_alt": "",
        "content_image_credit": "", "content_image_credit_url": "", "word_count": len(" ".join(body).split()),
        "display_source": False, "source_urls": list(dict.fromkeys(source_urls)),
        "source_links": list(dict.fromkeys(source_urls)),
    }
    active.append(article)
    ARTICLES.write_text(json.dumps(active, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[DIGEST] Created {ident} with {len(chosen)} items ({fresh_count} fresh, {supplement_count} older supplements).")
    for item in digest_items:
        marker = "[OLDER SUPPLEMENT]" if item["is_supplement"] else "[FRESH 24H]"
        print(f"[DIGEST] {marker} {item['number']}. {item['title']}")


if __name__ == "__main__":
    main()
