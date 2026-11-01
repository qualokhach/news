#!/usr/bin/env python3
"""Submit a manual topic/draft as a research lead; never publish directly."""
import os, json, re, hashlib, unicodedata
from pathlib import Path
from datetime import datetime, timezone
from content_quality import domain_key
ROOT=Path(__file__).resolve().parents[1]
pending_path=ROOT/'data/pending.json'
seen_path=ROOT/'data/seen_items.json'

title=os.getenv('ARTICLE_TITLE','').strip()
category=os.getenv('ARTICLE_CATEGORY','').strip()
summary=os.getenv('ARTICLE_SUMMARY','').strip()
raw=os.getenv('ARTICLE_BODY','').strip()
source_url=os.getenv('ARTICLE_SOURCE_URL','').strip()
source_name=os.getenv('ARTICLE_SOURCE_NAME','').strip()
source_date=os.getenv('ARTICLE_SOURCE_PUBLISHED_AT','').strip()
if not title or category not in {'vietnam','world','sports','technology'} or not summary:
    raise SystemExit('Missing title/summary or invalid category.')
if not source_url.startswith('https://'):
    raise SystemExit('A verified HTTPS source URL is required. Manual submissions are research leads, not direct publications.')
if len(raw.split())<100:
    raise SystemExit('Provide at least 100 words of context. This text is context only and will not be published as-is.')
now=datetime.now(timezone.utc).isoformat()
if source_date:
    try:
        dt=datetime.fromisoformat(source_date.replace('Z','+00:00'))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        source_date=dt.astimezone(timezone.utc).isoformat()
    except Exception:
        raise SystemExit('ARTICLE_SOURCE_PUBLISHED_AT must be an ISO-8601 date/time.')
else:
    raise SystemExit('ARTICLE_SOURCE_PUBLISHED_AT is required; do not invent a source publication date.')
ident=hashlib.sha256((source_url+title).encode()).hexdigest()[:20]
pending=json.loads(pending_path.read_text(encoding='utf-8')) if pending_path.exists() else []
if any(x.get('source_url')==source_url or x.get('id')==ident for x in pending):
    raise SystemExit('This source URL/topic is already present in the research queue.')
pending.append({
    'id':ident,'discovery_title':title[:240],'source_url':source_url,'source_name':source_name or 'User-submitted lead',
    'category':category,'source_published_at':source_date,'discovered_at':now,
    'source_terms_url':'','source_feed_domain':domain_key(source_url),
    'discovery_summary':summary[:1200],'manual_context':raw[:8000],
    'status':'queued','attempts':0,'origin':'manual_research_lead'
})
pending_path.write_text(json.dumps(pending[-5000:],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
seen=json.loads(seen_path.read_text(encoding='utf-8')) if seen_path.exists() else {'items':{}}
if not isinstance(seen,dict): seen={'items':{}}
seen.setdefault('items',{})[source_url]={'id':ident,'source_url':source_url,'title':title,'status':'queued','first_seen_at':now}
seen['last_manual_lead_at']=now
seen_path.write_text(json.dumps(seen,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Staged research lead {ident}; no article was published. The normal research and QA pipeline must pass it first.')
