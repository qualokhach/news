#!/usr/bin/env python3
"""Create a noon digest from AppNho-published articles only.

Unverified RSS leads are never used as digest items. New AppNho stories from the last 24 hours
are prioritized; older AppNho stories may supplement the list, with their original event/source
dates displayed so they cannot be mistaken for new events.
"""
import json, os, re, difflib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
ARTICLES=ROOT/'data/articles.json'
ARCHIVE=ROOT/'data/archive_articles.json'
CATALOG=ROOT/'data/archive_catalog.json'
MANIFEST=ROOT/'data/archive_manifest.json'
VN=ZoneInfo('Asia/Ho_Chi_Minh')
LABELS={'vietnam':'Việt Nam','world':'Thế giới','technology':'Công nghệ','sports':'Thể thao'}
BASE='https://appnho.io.vn/news/article.html?id='
MIN=6
MAX=10
HOURS=24

def load(path, default):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,type(default)) else default
    except (OSError,json.JSONDecodeError):
        return default

def clean(value):
    return re.sub(r'\s+',' ',str(value or '')).strip()

def dt(value):
    try:
        d=datetime.fromisoformat(str(value or '').replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError,TypeError):
        return None

def article_url(ident):
    return BASE+quote(str(ident),safe='')

def all_published_articles(active, archive, catalog, manifest):
    by_id={}
    full=active+archive
    archive_paths={'data/archive_articles.json'}
    for rel in manifest if isinstance(manifest,list) else []:
        if isinstance(rel,str) and rel.startswith('data/archive') and rel.endswith('.json'):
            archive_paths.add(rel)
    for item in catalog:
        rel=item.get('file') if isinstance(item,dict) else None
        if isinstance(rel,str) and rel.startswith('data/archive') and rel.endswith('.json'):
            archive_paths.add(rel)
    for rel in sorted(archive_paths):
        path=ROOT/rel
        if path.exists():
            batch=load(path,[])
            if rel!='data/archive_articles.json':
                full.extend(batch)
    for article in full:
        if isinstance(article,dict) and article.get('id'):
            old=by_id.get(str(article['id']))
            if old is None or (not old.get('body') and article.get('body')):
                by_id[str(article['id'])]=article
    return list(by_id.values())

def appnho_rows(articles, now):
    cutoff=now-timedelta(hours=HOURS)
    fresh=[]; older=[]; seen_ids=set()
    for article in articles:
        if article.get('content_type')=='news_digest':
            continue
        if article.get('quality_version')!='1.5' or article.get('quality_status')!='PASS':
            continue
        # Legacy records must have completed the evidence-based migration before
        # they can supplement a current digest. New v1.5 articles have no legacy flag.
        legacy_status=str(article.get('legacy_upgrade_status') or '').upper()
        if legacy_status and legacy_status!='PASS':
            continue
        ident=article.get('id')
        if not ident or str(ident) in seen_ids:
            continue
        seen_ids.add(str(ident))
        title=clean(article.get('title'))
        body=article.get('body') or []
        if isinstance(body,str): body=[body]
        summary=clean(article.get('summary')) or clean(' '.join(str(x) for x in body[:2]))
        if not ident or not title or len(summary)<35:
            continue
        app_pub=dt(article.get('appnho_published_at') or article.get('fetched_at') or article.get('published_at'))
        event_date=dt(article.get('published_at'))
        if not app_pub or app_pub>now:
            continue
        item={
            'id':str(ident),'title':title,'summary':summary[:620],
            'event_key':clean(article.get('event_id') or article.get('event_key') or ''),
            'category':article.get('category'),'appnho_published_at':app_pub.isoformat(),
            'event_date':event_date.isoformat() if event_date else '',
            'url':article_url(ident),'is_supplement':app_pub<cutoff
        }
        (fresh if app_pub>=cutoff else older).append(item)
    fresh.sort(key=lambda x:x['appnho_published_at'],reverse=True)
    older.sort(key=lambda x:x['appnho_published_at'],reverse=True)
    return fresh,older

def _same_event(item, chosen):
    key=clean(item.get('event_key')).casefold()
    title=clean(item.get('title')).casefold()
    for old in chosen:
        old_key=clean(old.get('event_key')).casefold()
        if key and old_key and key==old_key: return True
        old_title=clean(old.get('title')).casefold()
        if difflib.SequenceMatcher(None,title,old_title).ratio()>=0.78: return True
    return False

def choose_digest_items(fresh, older, minimum=MIN, maximum=MAX):
    chosen=[]; used=set(); supplements=0
    for item in fresh:
        if len(chosen)>=maximum: break
        if item['id'] in used or _same_event(item,chosen): continue
        chosen.append(item); used.add(item['id'])
    if len(chosen)<minimum:
        for item in older:
            if len(chosen)>=minimum: break
            if item['id'] in used or _same_event(item,chosen): continue
            chosen.append(item); used.add(item['id']); supplements+=1
    return chosen,supplements

def main():
    now=datetime.now(timezone.utc)
    active=load(ARTICLES,[])
    archive=load(ARCHIVE,[])
    catalog=load(CATALOG,[])
    manifest=load(MANIFEST,['data/archive_articles.json'])
    ident='diem-tin-'+now.astimezone(VN).date().isoformat()
    rebuild=os.getenv('REBUILD_DIGEST','').lower() in {'1','true','yes'}
    if any(isinstance(a,dict) and a.get('id')==ident for a in active+archive) and not rebuild:
        print("[DIGEST] Today's digest exists; set REBUILD_DIGEST=1 to rebuild.")
        return
    if rebuild:
        active=[a for a in active if not(isinstance(a,dict) and a.get('id')==ident)]
    all_articles=all_published_articles(active,archive,catalog,manifest)
    fresh,older=appnho_rows(all_articles,now)
    chosen,supplements=choose_digest_items(fresh,older)
    if len(chosen)<MIN:
        print(f"[DIGEST] Only {len(chosen)} AppNho articles available; need {MIN}. No digest published.")
        return
    date=now.astimezone(VN).strftime('%d/%m/%Y')
    title=f"Điểm tin AppNho trưa {date}: {len(chosen)} bài đáng chú ý"
    lead="Bản điểm tin chọn các bài AppNho News mới trong 24 giờ qua; những bài cũ hơn được ghi rõ ngày sự kiện hoặc ngày công bố để bạn phân biệt."
    items=[]
    for i,item in enumerate(chosen,1):
        event=dt(item.get('event_date'))
        app_date=dt(item.get('appnho_published_at'))
        if event and app_date and event.date()!=app_date.date():
            date_label='Sự kiện/nguồn: '+event.astimezone(VN).strftime('%d/%m/%Y')
        else:
            date_label='AppNho đăng: '+(app_date.astimezone(VN).strftime('%d/%m/%Y') if app_date else '')
        items.append({
            'number':i,'title':item['title'],'category':LABELS.get(item.get('category'),'Tin tức'),
            'summary':item['summary'],'url':item['url'],'article_id':item['id'],
            'published_at':item['appnho_published_at'],'event_date':item.get('event_date',''),
            'date_label':date_label,'is_supplement':bool(item['is_supplement'])
        })
    body=[lead]+[f"{x['number']}. {x['title']} — {x['summary']}" for x in items]
    digest={
        'id':ident,'title':title,'summary':lead,'category':'vietnam','source_name':'AppNho',
        'source_url':'','source_urls':[],'source_links':[],
        'published_at':now.isoformat(),'fetched_at':now.isoformat(),'appnho_published_at':now.isoformat(),
        'content_type':'news_digest','collection':'current','body':body,'digest_items':items,
        'digest_window_hours':HOURS,'digest_fresh_count':len(fresh[:MAX]),
        'digest_supplement_count':supplements,'generation_provider':'deterministic_digest',
        'seo_title':title[:70],'meta_description':lead[:160],
        'keywords':['điểm tin AppNho','tin Việt Nam','tin thế giới','tin công nghệ','tin thể thao'],
        'slug':ident,'images':[],'content_image_url':'','word_count':len(' '.join(body).split()),
        'display_source':False,'quality_version':'1.5','quality_status':'PASS',
        'editorial_value':'Tuyển chọn các bài AppNho News theo thời điểm xuất bản, có phân biệt bài mới và bài nhìn lại.'
    }
    active.append(digest)
    ARTICLES.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"[DIGEST] Created {ident}: {len(fresh[:MAX])} fresh AppNho articles, {supplements} older AppNho supplements.")
if __name__=='__main__':
    main()
