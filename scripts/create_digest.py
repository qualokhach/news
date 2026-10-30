#!/usr/bin/env python3
"""Build an editorially clean AppNho digest: unpublished source leads first, AppNho back-catalog only as fallback."""
import json, re, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
ARTICLES=ROOT/"data/articles.json"; ARCHIVE=ROOT/"data/archive_articles.json"; CATALOG=ROOT/"data/archive_catalog.json"; PENDING=ROOT/"data/pending.json"
VN=ZoneInfo("Asia/Ho_Chi_Minh"); LABELS={"vietnam":"Việt Nam","world":"Thế giới","technology":"Công nghệ","sports":"Thể thao"}
BASE="https://www.appnho.io.vn/news/article.html?id="; MIN=6; MAX=10; HOURS=24

def load(path):
    try:
        x=json.loads(path.read_text(encoding="utf-8")); return x if isinstance(x,list) else []
    except (OSError,json.JSONDecodeError): return []
def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()
def dt(x):
    try:
        d=datetime.fromisoformat(str(x or "").replace("Z","+00:00")); return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError,TypeError): return None
def appnho_rows(active,archive,catalog,now):
    by={}
    for a in active+archive+catalog:
        if isinstance(a,dict) and a.get("id") and a.get("content_type")!="news_digest":
            old=by.get(str(a["id"]))
            if old is None or (not old.get("body") and a.get("body")): by[str(a["id"])]=a
    out=[]
    for a in by.values():
        pub=dt(a.get("published_at")); title=clean(a.get("title")); summary=clean(a.get("summary")) or clean(" ".join(a.get("body",[])[:2]) if isinstance(a.get("body"),list) else a.get("body"))
        if not pub or pub>now or not title or not summary: continue
        out.append({"title":title,"summary":summary,"category":a.get("category"),"published_at":pub.isoformat(),"source_url":a.get("source_url"),"url":BASE+quote(str(a["id"]),safe=""),"is_appnho":True,"is_supplement":True})
    return sorted(out,key=lambda x:x["published_at"],reverse=True)
def main():
    now=datetime.now(timezone.utc); today=now.astimezone(VN).date().isoformat(); active=load(ARTICLES); archive=load(ARCHIVE); catalog=load(CATALOG); pending=load(PENDING)
    ident="diem-tin-"+today; rebuild=os.getenv("REBUILD_DIGEST","").lower() in ("1","true","yes")
    exists=any(isinstance(a,dict) and a.get("id")==ident for a in active+archive+catalog)
    if exists and not rebuild: print("[DIGEST] Today's digest exists; set REBUILD_DIGEST=1 to rebuild."); return
    if rebuild: active=[a for a in active if not(isinstance(a,dict) and a.get("id")==ident)]
    published_urls={clean(a.get("source_url")) for a in active+archive+catalog if isinstance(a,dict) and a.get("source_url")}
    cutoff=now-timedelta(hours=HOURS); fresh=[]; seen_urls=set(); seen_titles=set()
    for x in pending:
        if not isinstance(x,dict) or x.get("status") not in ("queued","pending","retry"): continue
        pub=dt(x.get("source_published_at")); url=clean(x.get("source_url")); title=clean(x.get("discovery_title")); summary=clean(x.get("discovery_summary") or x.get("description") or x.get("summary"))
        if not pub or pub<cutoff or pub>now or not url.startswith("http") or url in published_urls or not title or not summary: continue
        key=re.sub(r"[^a-z0-9\u00c0-\u024f]","",title.casefold())
        if url in seen_urls or (key and key in seen_titles): continue
        seen_urls.add(url); seen_titles.add(key)
        fresh.append({"title":title,"summary":summary[:420],"category":x.get("category"),"published_at":pub.isoformat(),"source_url":url,"url":"","is_appnho":False,"is_supplement":False})
    fresh.sort(key=lambda x:x["published_at"],reverse=True)
    chosen=fresh[:MAX]
    supplement_count=0
    if len(chosen)<MIN:
        existing=appnho_rows(active,archive,catalog,now)
        chosen_urls={x.get("source_url") for x in chosen}
        for x in existing:
            if len(chosen)>=MIN: break
            if x.get("source_url") in chosen_urls: continue
            chosen.append(x); chosen_urls.add(x.get("source_url")); supplement_count+=1
    if len(chosen)<MIN:
        print(f"[DIGEST] Only {len(chosen)} eligible stories with summaries; need {MIN}. No digest published."); return
    date=now.astimezone(VN).strftime("%d/%m/%Y"); title=f"Điểm tin AppNho trưa {date}: {len(chosen)} tin đáng chú ý"
    lead="Mời bạn cùng AppNho điểm lại những bản tin đáng chú ý vừa diễn ra trong nước và trên thế giới."
    items=[]; source_urls=[]
    for i,x in enumerate(chosen,1):
        item={"number":i,"title":x["title"],"category":LABELS.get(x.get("category"),"Tin tức"),"summary":x["summary"],"url":x.get("url") or "","published_at":x["published_at"],"is_supplement":bool(x["is_supplement"])}
        items.append(item)
        if x.get("source_url"): source_urls.append(x["source_url"])
    body=[lead]+[f"{x['number']}. {x['title']} — {x['summary']}" for x in items]
    article={"id":ident,"title":title,"summary":lead,"category":"vietnam","source_name":"AppNho tổng hợp","source_url":"","published_at":now.isoformat(),"fetched_at":now.isoformat(),"content_type":"news_digest","collection":"current","body":body,"digest_items":items,"digest_window_hours":HOURS,"digest_fresh_count":len(fresh),"digest_supplement_count":supplement_count,"generation_provider":"deterministic_digest","seo_title":title[:70],"meta_description":lead,"keywords":["điểm tin","tin Việt Nam","tin thế giới","tin công nghệ","tin thể thao"],"slug":ident,"images":[],"content_image_url":"","word_count":len(" ".join(body).split()),"display_source":False,"source_urls":list(dict.fromkeys(source_urls)),"source_links":list(dict.fromkeys(source_urls))}
    active.append(article); ARTICLES.write_text(json.dumps(active,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"[DIGEST] Created {ident}: {len(fresh)} new external leads, {supplement_count} AppNho back-catalog supplements.")
if __name__=="__main__": main()
