#!/usr/bin/env python3
"""Build RSS, sitemap and server-side social preview metadata from published articles."""
import html
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.appnho.io.vn/news/"
CATEGORY_IMAGES = {
    "world": "https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_gioi.png",
    "vietnam": "https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Viet_Nam.png",
    "sports": "https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_thao.png",
    "technology": "https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Cong_Nghe.png",
}

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

active = read_json(ROOT / "data/articles.json", [])
archive = read_json(ROOT / "data/archive_articles.json", [])
catalog = read_json(ROOT / "data/archive_catalog.json", [])
manifest = read_json(ROOT / "data/archive_manifest.json", [])

# Include archived batches referenced by the manifest/catalog without changing any source data.
archive_paths = set()
for item in manifest if isinstance(manifest, list) else []:
    if isinstance(item, str) and item.startswith("data/") and item.endswith(".json"):
        archive_paths.add(item)
for item in catalog if isinstance(catalog, list) else []:
    path = item.get("file") if isinstance(item, dict) else None
    if isinstance(path, str) and path.startswith("data/") and path.endswith(".json"):
        archive_paths.add(path)
for rel in sorted(archive_paths):
    candidate = (ROOT / rel).resolve()
    if ROOT.resolve() not in candidate.parents:
        continue
    extra = read_json(candidate, [])
    if isinstance(extra, list):
        archive.extend(extra)

# Prefer full article records over catalog-only records; never write to article data files.
by_id = {}
for article in active + archive + catalog:
    if isinstance(article, dict) and article.get("id"):
        by_id.setdefault(str(article["id"]), article)
articles = list(by_id.values())

def article_url(ident):
    return BASE + "article.html?id=" + quote(str(ident), safe="")

urls = [BASE, BASE + "about.html"]
items = []
metadata = {}
for article in articles:
    ident = str(article["id"])
    url = article_url(ident)
    urls.append(url)
    title = str(article.get("seo_title") or article.get("title") or "AppNho News").strip()
    description = str(article.get("meta_description") or article.get("summary") or title).strip()
    # Prefer a story-specific image; category artwork is only a fallback.
    image = (article.get("image_thumbnail") or article.get("content_image_url") or
             article.get("thumbnail") or CATEGORY_IMAGES.get(article.get("category"), ""))
    metadata[ident] = {
        "id": ident,
        "title": title,
        "description": description[:300],
        "url": url,
        "image": str(image or ""),
        "published_at": str(article.get("published_at") or ""),
        "category": str(article.get("category") or "news"),
    }

for article in sorted(articles, key=lambda x: x.get("published_at", ""), reverse=True)[:100]:
    ident = article.get("id")
    if not ident:
        continue
    link = article_url(ident)
    title = html.escape(str(article.get("title") or ""))
    desc = html.escape(str(article.get("summary") or ""))
    pub = str(article.get("published_at") or "")
    try:
        pub = datetime.fromisoformat(pub.replace("Z", "+00:00")).strftime("%a, %d %b %Y %H:%M:%S GMT")
    except ValueError:
        pub = ""
    items.append(f"<item><title>{title}</title><link>{html.escape(link)}</link><guid isPermaLink=\"false\">{html.escape(str(ident))}</guid><description>{desc}</description>" + (f"<pubDate>{pub}</pubDate>" if pub else "") + "</item>")

(ROOT / "social_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
unique = list(dict.fromkeys(urls))
(ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(f"  <url><loc>{html.escape(u)}</loc></url>\n" for u in unique) + "</urlset>\n", encoding="utf-8")
(ROOT / "feed.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>AppNho News</title><link>' + BASE + '</link><description>Tin tức do AppNho biên tập</description>' + ''.join(items) + '</channel></rss>\n', encoding="utf-8")
print(f"Built sitemap for {len(unique)} URLs, RSS feed for {len(items)} articles and social metadata for {len(metadata)} articles.")
