#!/usr/bin/env python3
"""Build RSS, sitemap and server-readable static Open Graph share pages."""
import json, html, re
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
BASE="https://appnho.io.vn/news/"
THUMBS={
 'world':'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_gioi.png',
 'vietnam':'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Viet_Nam.png',
 'sports':'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_the_thao.png',
 'technology':'https://res.cloudinary.com/wnlmpwor/image/upload/v1792675323/tin_Cong_Nghe.png',
}
def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
active=read_json(ROOT/'data/articles.json',[])
archive=read_json(ROOT/'data/archive_articles.json',[])
catalog=read_json(ROOT/'data/archive_catalog.json',[])
by_id={}
for article in archive+active:
    if article.get('id'): by_id.setdefault(str(article['id']),article)
for entry in catalog:
    if entry.get('id'): by_id.setdefault(str(entry['id']),entry)
articles=list(by_id.values())
articles.sort(key=lambda x: str(x.get('published_at') or ''), reverse=True)
urls=[BASE,BASE+'about.html']
items=[]
for a in articles:
    ident=str(a.get('id') or '')
    if not ident: continue
    safe=quote(ident,safe='')
    share_url=BASE+'share/'+safe+'/index.html'
    legacy_url=BASE+'article.html?id='+safe
    urls.extend([share_url,legacy_url])
    title=html.escape(str(a.get('title','')))
    desc=html.escape(str(a.get('summary','')))
    pub=a.get('published_at','')
    try: pub=datetime.fromisoformat(pub.replace('Z','+00:00')).strftime('%a, %d %b %Y %H:%M:%S GMT')
    except Exception: pub=''
    items.append(f'<item><title>{title}</title><link>{html.escape(share_url)}</link><guid isPermaLink="false">{html.escape(ident)}</guid><description>{desc}</description>'+(f'<pubDate>{pub}</pubDate>' if pub else '')+'</item>')
    # Prefer an actual editorial image, then a category illustration. Always absolute HTTPS.
    image=str(a.get('content_image_url') or a.get('image_thumbnail') or THUMBS.get(a.get('category','')) or '')
    if not image.startswith('https://'): image=THUMBS.get(a.get('category',''), '')
    alt=str(a.get('content_image_alt') or ('Ảnh minh họa: '+str(a.get('title',''))))
    description=str(a.get('meta_description') or a.get('summary') or a.get('title') or '')[:300]
    # A static HTML document lets social crawlers read OG metadata without executing JS.
    # Human visitors are redirected to the existing fully featured article renderer.
    redirect=html.escape(legacy_url,quote=True)
    page='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+html.escape(str(a.get('seo_title') or a.get('title') or 'AppNho News'))+''' | AppNho News</title>
<meta name="description" content="'''+html.escape(description,quote=True)+'''">
<meta property="og:type" content="article"><meta property="og:title" content="'''+html.escape(str(a.get('seo_title') or a.get('title') or ''),quote=True)+'''">
<meta property="og:description" content="'''+html.escape(description,quote=True)+'''"><meta property="og:url" content="'''+html.escape(share_url,quote=True)+'''">
<meta property="og:site_name" content="AppNho News"><meta property="og:locale" content="vi_VN">
<meta property="og:image" content="'''+html.escape(image,quote=True)+'''"><meta property="og:image:secure_url" content="'''+html.escape(image,quote=True)+'''">
<meta property="og:image:alt" content="'''+html.escape(alt,quote=True)+'''"><meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="'''+html.escape(str(a.get('seo_title') or a.get('title') or ''),quote=True)+'''"><meta name="twitter:description" content="'''+html.escape(description,quote=True)+'''"><meta name="twitter:image" content="'''+html.escape(image,quote=True)+'''">
<link rel="canonical" href="'''+html.escape(share_url,quote=True)+'''">
<script>window.location.replace("'''+redirect+'''");</script></head><body><p>Đang mở bài viết… <a href="'''+redirect+'''">Nhấn vào đây nếu trang không tự chuyển.</a></p></body></html>'''
    target=ROOT/'share'/quote(ident,safe='')/'index.html'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(page,encoding='utf-8')
unique=list(dict.fromkeys(urls))
(ROOT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+''.join(f'  <url><loc>{html.escape(u)}</loc></url>\n' for u in unique)+'</urlset>\n',encoding='utf-8')
(ROOT/'feed.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>AppNho News</title><link>'+BASE+'</link><description>Tin tức do AppNho biên tập</description>'+''.join(items[:100])+'</channel></rss>\n',encoding='utf-8')
print(f'Built sitemap for {len(unique)} URLs, RSS for {min(len(items),100)} articles, and {len(articles)} static share pages.')
