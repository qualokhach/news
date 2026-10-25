#!/usr/bin/env python3
"""Close the current article batch once its oldest article has been live for 30 days.
Closed JSON batches are immutable; only the catalog/manifest and active file change at rotation.
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
ACTIVE=DATA/'articles.json'
CATALOG=DATA/'archive_catalog.json'
MANIFEST=DATA/'archive_manifest.json'
BATCH_DIR=DATA/'archive_batches'
CLOSE_AFTER_DAYS=30

def load(path, default):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8'))

def parse_dt(article):
    raw=article.get('published_at') or article.get('fetched_at') or ''
    try:
        dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def main():
    active=load(ACTIVE,[])
    if not active:
        print('[ROTATE] No active articles; nothing to close.')
        return
    now=datetime.now(timezone.utc)
    dated=[(parse_dt(a),a) for a in active]
    valid=[dt for dt,a in dated if dt]
    if not valid:
        print('[ROTATE] No valid publication dates; nothing closed.')
        return
    oldest=min(valid)
    if now-oldest < timedelta(days=CLOSE_AFTER_DAYS):
        print(f'[ROTATE] Active batch age is {(now-oldest).days} days; closes after {CLOSE_AFTER_DAYS} days.')
        return
    # Close the whole active batch at once, then start a fresh empty batch.
    # This makes each archive file a roughly 30-day immutable snapshot.
    closing=list(active)
    remaining=[]
    BATCH_DIR.mkdir(parents=True,exist_ok=True)
    dates=sorted((parse_dt(a).astimezone(timezone.utc).date().isoformat() for a in closing if parse_dt(a)))
    filename=f"articles-{dates[0]}-to-{dates[-1]}.json"
    target=BATCH_DIR/filename
    if target.exists():
        raise SystemExit(f'[ROTATE] Refusing to overwrite closed batch: {target.relative_to(ROOT)}')
    for a in closing:
        a['collection']='archive'
    target.write_text(json.dumps(closing,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rel='data/archive_batches/'+filename
    manifest=load(MANIFEST,['data/archive_articles.json'])
    if rel not in manifest: manifest.append(rel)
    catalog=load(CATALOG,[])
    existing={x.get('id') for x in catalog}
    for a in closing:
        if a.get('id') in existing:
            raise SystemExit(f'[ROTATE] Duplicate ID in archive catalog: {a.get("id")}')
        catalog.append({k:a.get(k) for k in ['id','title','summary','category','published_at','fetched_at','keywords','slug','seo_title','meta_description']} | {'file':rel,'collection':'archive'})
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ACTIVE.write_text(json.dumps(remaining,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'[ROTATE] Closed {len(closing)} articles to {rel}; {len(remaining)} remain active. Closed batch file will never be overwritten.')
if __name__=='__main__': main()
