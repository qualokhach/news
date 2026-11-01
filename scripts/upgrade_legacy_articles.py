#!/usr/bin/env python3
"""Upgrade already-published AppNho News articles in bounded, evidence-based batches.

Existing URLs, IDs and original publication/event dates are preserved. An article is only
rewritten when current source evidence supports a new fact ledger and it passes v1.5 QA.
A HOLD is automatic and never waits for a GitHub/manual approval.
"""
import json, os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from news_pipeline import (
    ROOT, ARTICLES, ARCHIVE, generate_with_fallback, extract_page, source_info,
    search_official_sources, make_article, domain_key, canon, clean, now_iso, robots_allowed, evidence_matches_title
)

CATALOG=ROOT/'data/archive_catalog.json'
MANIFEST=ROOT/'data/archive_manifest.json'
REPORT_DIR=ROOT/'reports'
MAX_SUCCESS=int(os.getenv('MAX_LEGACY_UPGRADES_PER_RUN','3'))
MAX_ATTEMPTS=int(os.getenv('MAX_LEGACY_ATTEMPTS_PER_RUN','12'))
# Published legacy content is never rewritten by a scheduled job. Apply requires an explicit manual opt-in.
DRY_RUN=os.getenv('LEGACY_UPGRADE_APPLY','').lower() not in {'1','true','yes'}

def load(path, default):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,type(default)) else default
    except (OSError,json.JSONDecodeError):
        return default

def parse_dt(value):
    try:
        d=datetime.fromisoformat(str(value or '').replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except Exception:
        return None

def source_candidates(article):
    urls=[]
    for key in ('source_url','source_urls','source_links'):
        value=article.get(key)
        if isinstance(value,str): urls.append(value)
        elif isinstance(value,list): urls.extend(value)
    refs=article.get('source_references',[])
    for ref in refs if isinstance(refs,list) else []:
        if isinstance(ref,dict): urls.append(ref.get('url',''))
    out=[]
    for url in urls:
        url=canon(str(url or ''))
        if url.startswith('https://') and url not in out and 'appnho.io.vn' not in url:
            out.append(url)
    return out[:8]

def make_upgrade_prompt(article, source_items, evidence):
    source_payload=[]
    for item in source_items:
        url=item['source_url']
        info=source_info(url)
        source_payload.append({
            'name':item['source_name'],'url':url,'source_type':info.get('source_type'),
            'is_primary_candidate':info.get('is_primary',False),
            'headline':item.get('discovery_title',''),
            'published_at':item.get('source_published_at',''),
            'evidence':evidence.get(url,'')[:6500]
        })
    old_body=article.get('body') or []
    if isinstance(old_body,str): old_body=[old_body]
    context={
        'old_title':article.get('title',''),
        'old_summary':article.get('summary',''),
        'old_body_for_context_only':' '.join(str(x) for x in old_body)[:6500],
        'original_event_date':article.get('published_at',''),
        'category':article.get('category','')
    }
    instructions=r'''Bạn đang nâng cấp một bài AppNho News đã xuất bản lên tiêu chuẩn v1.5.
Bài cũ chỉ là ngữ cảnh để nhận biết đề tài; KHÔNG được xem nội dung bài cũ là bằng chứng. Chỉ sử dụng chứng cứ trong nguồn mới được cung cấp.
Trả về JSON với đúng các trường:
{"publish":true/false,"reason":"...","title":"...","summary":"...","category":"world|vietnam|sports|technology","seo_title":"...","meta_description":"...","keywords":["..."],"body":["đoạn 1"],"source_index":0,"editorial_value":"đóng góp biên tập cụ thể","risk_level":"R1|R2|R3","content_type":"quick_update|short_explainer|news_analysis|long_analysis","data_type":"general","freshness_ttl_hours":24,"fact_ledger":[{"claim":"dữ kiện có thể kiểm tra","source_urls":["URL chính xác trong danh sách nguồn"],"evidence_snippet":"trích đoạn hỗ trợ claim","evidence_locator":"heading/đoạn/bảng","importance":"core|supporting"}]}
Yêu cầu:
- Viết lại thực chất, không chỉ thay từ. Giữ các dữ kiện cũ chỉ khi nguồn mới xác nhận.
- Không tự bịa chi tiết để lấp khoảng trống. Nếu không đủ nguồn, trả publish=false.
- Cần ít nhất 3 dữ kiện trong fact_ledger, mỗi dữ kiện trỏ tới URL chính xác và có evidence_snippet cùng evidence_locator.
- Cần ít nhất hai miền nguồn độc lập, trừ khi có một nguồn chính thức/gốc đủ thẩm quyền cho sự kiện đơn nguồn.
- R2 cần nguồn chính thức hoặc ít nhất ba miền nguồn độc lập. R3 chỉ viết tường thuật/thông tin chung khi có nguồn chính thức; không đưa lời khuyên cá nhân về sức khỏe, tài chính, pháp luật hoặc an toàn.
- Chọn thể loại phù hợp: quick_update >=180 từ, short_explainer >=350, news_analysis >=600, long_analysis >=700; ít nhất 4 đoạn có chức năng riêng.
- Giá trị biên tập phải cụ thể: dữ liệu nào được đặt vào bối cảnh, điều gì được so sánh, tác động nào có chứng cứ, hoặc giới hạn nào được làm rõ.
- Không tạo lời kể AppNho đã phỏng vấn, khảo sát, tác nghiệp thực địa hay trải nghiệm trực tiếp.
- Không đưa ghi chú nội bộ, trạng thái QA hoặc câu “AI tổng hợp”.
- Không thay đổi bản chất/ngày của sự kiện. published_at là ngày sự kiện/nguồn; AppNho giữ ngày xuất bản gốc riêng.
- Chỉ trả JSON hợp lệ, không markdown.
Bài cũ (chỉ để nhận diện đề tài):
'''
    return instructions+json.dumps(context,ensure_ascii=False)+"\n\nNguồn mới:\n"+json.dumps(source_payload,ensure_ascii=False)

def gather_evidence(article):
    urls=source_candidates(article)
    sources=[]; evidence={}; seen_domains=set()
    for url in urls:
        domain=domain_key(url)
        info=source_info(url)
        # Previously cited media pages are discovery references, not primary evidence.
        if not info.get('is_primary'):
            continue
        if info.get('access_status')!='RESEARCH_ALLOWED' or info.get('terms_status')!='VERIFIED':
            print(f'[INFO] Legacy source not approved for research: {domain}')
            continue
        if domain and domain in seen_domains: continue
        try:
            if not robots_allowed(url):
                continue
            text=extract_page(url)
            if len(text)>500 and evidence_matches_title(article.get('title',''),text):
                info=source_info(url)
                sources.append({
                    'source_name':info.get('name') or domain,
                    'source_url':url,
                    'source_published_at':article.get('published_at',''),
                    'discovery_title':article.get('title',''),
                    'category':article.get('category','')
                })
                evidence[url]=text
                if domain: seen_domains.add(domain)
        except Exception as e:
            print(f"[INFO] Legacy source unavailable {domain}: {type(e).__name__}")
    if len(seen_domains)<2:
        official=search_official_sources(article.get('title',''),article.get('category',''),seen_domains,limit=3)
        for item in official:
            try:
                info=source_info(item['source_url'])
                if info.get('access_status')!='RESEARCH_ALLOWED' or info.get('terms_status')!='VERIFIED':
                    continue
                if not robots_allowed(item['source_url']):
                    continue
                text=extract_page(item['source_url'])
                if len(text)>500 and evidence_matches_title(item.get('discovery_title',''),text):
                    sources.append(item)
                    evidence[item['source_url']]=text
                    seen_domains.add(domain_key(item['source_url']))
            except Exception as e:
                print(f"[INFO] Legacy primary source unavailable: {type(e).__name__}")
    return sources,evidence

def update_article(original, rewritten):
    keep={k:original.get(k) for k in ('id','slug','collection','published_at','fetched_at','appnho_published_at','origin')}
    for key in ('title','summary','category','body','seo_title','meta_description','keywords','source_name','source_url',
                'source_urls','source_links','source_references','fact_ledger','editorial_value','risk_level',
                'verification_timestamp','freshness_ttl_hours','quality_version','quality_status','quality_audit',
                'generation_provider','word_count'):
        if key in rewritten:
            original[key]=rewritten[key]
    for key,value in keep.items():
        if value is not None:
            original[key]=value
    if not original.get('appnho_published_at'):
        original['appnho_published_at']=original.get('fetched_at') or original.get('published_at')
    original.pop('editorial_note',None)
    original['updated_at']=now_iso()
    original['legacy_upgrade_status']='PASS'
    original['legacy_upgrade_last_attempt_at']=now_iso()
    original['legacy_upgrade_reason']='Rewritten from current source evidence and passed v1.5 QA.'
    return original

def main():
    active=load(ARTICLES,[])
    catalog=load(CATALOG,[])
    manifest=load(MANIFEST,['data/archive_articles.json'])
    archive_paths={'data/archive_articles.json'}
    for rel in manifest:
        if isinstance(rel,str) and rel.startswith('data/archive') and rel.endswith('.json'):
            archive_paths.add(rel)
    for item in catalog:
        rel=item.get('file') if isinstance(item,dict) else None
        if isinstance(rel,str) and rel.startswith('data/archive') and rel.endswith('.json'):
            archive_paths.add(rel)
    archive_data={}
    for rel in sorted(archive_paths):
        path=ROOT/rel
        if path.exists():
            archive_data[rel]=load(path,[])
    records=[]
    for item in active:
        if isinstance(item,dict): records.append(('data/articles.json',item))
    for rel,items in archive_data.items():
        for item in items:
            if isinstance(item,dict): records.append((rel,item))
    now=datetime.now(timezone.utc)
    eligible=[]
    for rel,article in records:
        if article.get('content_type')=='news_digest':
            article['legacy_upgrade_status']='EXEMPT_DIGEST'
            continue
        if article.get('quality_version')=='1.5' and article.get('quality_status')=='PASS':
            article['legacy_upgrade_status']='PASS'
            continue
        retry_after=parse_dt(article.get('legacy_upgrade_retry_after'))
        if article.get('legacy_upgrade_status')=='HOLD' and retry_after and retry_after>now:
            continue
        eligible.append((rel,article))
    eligible.sort(key=lambda x:(0 if x[0]=='data/articles.json' else 1,
                                parse_dt(x[1].get('appnho_published_at') or x[1].get('fetched_at') or x[1].get('published_at')) or now))
    successes=0; attempts=0; holds=0
    for rel,article in eligible:
        if successes>=MAX_SUCCESS or attempts>=MAX_ATTEMPTS:
            break
        attempts+=1
        ident=article.get('id','')
        print(f"[LEGACY] Checking {ident}: {article.get('title','')[:100]}")
        sources,evidence=gather_evidence(article)
        refs=[{'url':x['source_url'],'is_primary':source_info(x['source_url']).get('is_primary',False)} for x in sources]
        domains=len({domain_key(x['source_url']) for x in sources if domain_key(x['source_url'])})
        primary=any(x['is_primary'] for x in refs)
        if len(evidence)==0 or (domains<2 and not primary):
            reason='Không thu thập được đủ chứng cứ mới từ hai miền độc lập hoặc một nguồn chính thức.'
            article['legacy_upgrade_status']='HOLD'
            article['legacy_upgrade_reason']=reason
            article['legacy_upgrade_last_attempt_at']=now.isoformat()
            article['legacy_upgrade_retry_after']=(now+timedelta(days=3)).isoformat()
            holds+=1
            print(f"[HOLD] {ident}: {reason}")
            continue
        try:
            result,provider=generate_with_fallback(make_upgrade_prompt(article,sources,evidence))
            if not result.get('publish'):
                reason=clean(result.get('reason') or 'AI đánh giá chứng cứ chưa đủ')[:500]
                article['legacy_upgrade_status']='HOLD'
                article['legacy_upgrade_reason']=reason
                article['legacy_upgrade_last_attempt_at']=now.isoformat()
                article['legacy_upgrade_retry_after']=(now+timedelta(days=3)).isoformat()
                holds+=1
                print(f"[HOLD] {ident}: {reason}")
                continue
            result['_provider']=provider
            rewritten=make_article(result,sources)
            if not rewritten:
                raise ValueError('Generated legacy rewrite failed article validation')
            rewritten['generation_provider']=provider
            rewritten['origin']=article.get('origin','legacy_upgrade')
            # Do not carry forward an old image whose commercial license has not been re-verified.
            # The new article remains valid without an image; a separately verified image may be added later.
            update_article(article,rewritten)
            successes+=1
            print(f"[UPGRADED] {ident}: {article.get('word_count')} words; preserved ID/date/slug.")
        except Exception as e:
            article['legacy_upgrade_status']='HOLD'
            article['legacy_upgrade_reason']=str(e)[:500]
            article['legacy_upgrade_last_attempt_at']=now.isoformat()
            article['legacy_upgrade_retry_after']=(now+timedelta(hours=12)).isoformat()
            holds+=1
            print(f"[HOLD] {ident}: {type(e).__name__}: {str(e)[:220]}")
    if DRY_RUN:
        print('[LEGACY] DRY RUN: no article data files written.')
        return
    ARTICLES.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for rel,items in archive_data.items():
        (ROOT/rel).write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    full_by_id={}
    for _,article in records:
        if article.get('id'): full_by_id[str(article['id'])]=article
    for item in catalog:
        full=full_by_id.get(str(item.get('id')))
        if full:
            for key in ('title','summary','category','published_at','fetched_at','updated_at','keywords','slug','seo_title','meta_description','quality_status','quality_version','legacy_upgrade_status'):
                if key in full: item[key]=full[key]
    CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    report={'run_at':now.isoformat(),'eligible_at_start':len(eligible),'attempted':attempts,'upgraded':successes,'held':holds,
            'remaining_unreviewed':sum(1 for _,a in records if a.get('content_type')!='news_digest' and a.get('quality_version')!='1.5')}
    (REPORT_DIR/'legacy_upgrade_last_run.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('[LEGACY SUMMARY] '+json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    main()
