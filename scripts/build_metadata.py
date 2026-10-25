#!/usr/bin/env python3
"""Regenerate static RSS and sitemap from the GitHub-hosted article archive."""
import json, html
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
BASE="https://appnho.io.vn/news/"
active=json.loads((ROOT/"data/articles.json").read_text(encoding="utf-8"))
archive_path=ROOT/"data/archive_articles.json"
archive=json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else []
catalog_path=ROOT/"data/archive_catalog.json"
catalog=json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else []
articles=archive+[x for x in catalog if x.get("file")!="data/archive_articles.json"]+active
urls=[BASE, BASE+"about.html"]
for a in articles:
    ident=a.get("id")
    if ident:
        from urllib.parse import quote
        urls.append(BASE+"article.html?id="+quote(str(ident),safe=""))
unique=list(dict.fromkeys(urls))
items=[]
for a in sorted(articles,key=lambda x:x.get("published_at", ""),reverse=True)[:100]:
    ident=a.get("id")
    if not ident: continue
    link=BASE+"article.html?id="+__import__('urllib.parse',fromlist=['quote']).quote(str(ident),safe="")
    title=html.escape(a.get("title", ""))
    desc=html.escape(a.get("summary", ""))
    pub=a.get("published_at", "")
    try: pub=datetime.fromisoformat(pub.replace("Z","+00:00")).strftime("%a, %d %b %Y %H:%M:%S GMT")
    except Exception: pub=""
    items.append(f"<item><title>{title}</title><link>{html.escape(link)}</link><guid isPermaLink=\"false\">{html.escape(str(ident))}</guid><description>{desc}</description>"+(f"<pubDate>{pub}</pubDate>" if pub else "")+"</item>")
(ROOT/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+''.join(f'  <url><loc>{html.escape(u)}</loc></url>\n' for u in unique)+'</urlset>\n',encoding="utf-8")
(ROOT/"feed.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>AppNho News</title><link>'+BASE+'</link><description>Tin tức do AppNho biên tập</description>'+''.join(items)+'</channel></rss>\n',encoding="utf-8")
print(f"Built sitemap for {len(unique)} URLs and RSS feed for {len(items)} articles.")
