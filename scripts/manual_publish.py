#!/usr/bin/env python3
"""Validate and append a manual article from GitHub Actions workflow inputs."""
import os, json, re, hashlib, unicodedata
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/"data/articles.json"
def slugify(value):
    value=unicodedata.normalize("NFKD",value).encode("ascii","ignore").decode().lower()
    return re.sub(r"-+","-",re.sub(r"[^a-z0-9]+","-",value)).strip("-")[:72] or "article"
title=os.getenv("ARTICLE_TITLE","").strip()
category=os.getenv("ARTICLE_CATEGORY","").strip()
summary=os.getenv("ARTICLE_SUMMARY","").strip()
raw=os.getenv("ARTICLE_BODY","").strip()
body=[x.strip() for x in re.split(r"\n\s*\n",raw) if x.strip()]
words=len(raw.split())
if not title or category not in {"vietnam","world","sports","technology"} or not summary:
    raise SystemExit("Missing title/summary or invalid category.")
if words<600 or len(body)<6:
    raise SystemExit(f"Article rejected: {words} words, {len(body)} paragraphs; require at least 600 words and 6 paragraphs.")
source_url=os.getenv("ARTICLE_SOURCE_URL","").strip()
if source_url and not source_url.startswith(("https://","http://")):
    raise SystemExit("Source URL must begin with https:// or http://")
articles=json.loads(path.read_text(encoding="utf-8"))
archive_path=ROOT/"data/archive_articles.json"
archive=json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else []
catalog_path=ROOT/"data/archive_catalog.json"
catalog=json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else []
all_articles=archive+catalog+articles
if any(a.get("title","").strip().casefold()==title.casefold() for a in all_articles):
    raise SystemExit("An article with this exact title already exists; refusing duplicate.")
published=datetime.now(timezone.utc).isoformat()
base=slugify(title)
ident=base+"-"+hashlib.sha256((title+published).encode()).hexdigest()[:8]
keywords=[x.strip()[:60] for x in os.getenv("ARTICLE_KEYWORDS","").split(",") if x.strip()][:8]
article={"id":ident,"title":title,"summary":summary[:360],"category":category,"source_name":os.getenv("ARTICLE_SOURCE_NAME","").strip(),"source_url":source_url,"published_at":published,"fetched_at":published,"content_type":"manual_editorial","collection":"current","body":body,"origin":"manual","seo_title":title[:70],"meta_description":summary[:160],"keywords":keywords,"slug":ident,"images":[],"content_image_url":"","content_image_alt":"","content_image_credit":"","content_image_credit_url":"","word_count":words,"display_source":bool(source_url)}
articles.append(article)
path.write_text(json.dumps(articles,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"Added manual article {ident}; active file now contains {len(articles)} articles; historical archive contains {len(archive)}.")
