#!/usr/bin/env python3
"""Publish only researched, quality-gated candidates from data/research_queue.json."""
import json, os, sys, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from content_quality import validate_article_quality, validate_fact_ledger_proof, normalize_evidence_text, source_independence, domain_key, validate_r3_content, ttl_for_data_type
import news_pipeline as research_pipeline

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/'data/research_queue.json'
ARTICLES=ROOT/'data/articles.json'
PENDING=ROOT/'data/pending.json'
SEEN=ROOT/'data/seen_items.json'
LOG=ROOT/'data/publish_log.json'
UA='AppNhoNewsBot/1.0 (+https://github.com/qualokhach/news)'
MAX_PER_SLOT=int(os.getenv('MAX_ARTICLES_PER_SLOT','4'))
SLOT_KIND=os.getenv('NEWS_SLOT_KIND','regular')

def load(path, default):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,type(default)) else default
    except (OSError,json.JSONDecodeError):
        return default

def dt(value):
    try:
        d=datetime.fromisoformat(str(value or '').replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except Exception:
        return None

def robots_allowed(url):
    parts=urlsplit(url)
    robots_url=f'{parts.scheme}://{parts.netloc}/robots.txt'
    parser=RobotFileParser()
    parser.set_url(robots_url)
    try:
        req=Request(robots_url,headers={'User-Agent':UA})
        with urlopen(req,timeout=5) as response:
            raw=response.read(256_000).decode('utf-8','replace')
        parser.parse(raw.splitlines())
        return parser.can_fetch(UA,url)
    except HTTPError as e:
        if e.code==404:
            parser.parse([])
            return True
        return False
    except Exception:
        return False

def check_source_access(url):
    """Final lightweight GET check; avoids false negatives from publishers that reject HEAD."""
    if not str(url).startswith('https://'):
        return False, 'source URL must use HTTPS'
    if not robots_allowed(url):
        return False, 'robots.txt disallows or could not be verified'
    try:
        req=Request(url,headers={
            'User-Agent':UA,
            'Accept':'text/html,application/xhtml+xml,*/*;q=0.5',
            'Range':'bytes=0-4095'
        },method='GET')
        with urlopen(req,timeout=10) as response:
            if response.status in (200,206):
                # Read only a small prefix even if the server ignores the Range header.
                response.read(4096)
                return True,f'GET HTTP {response.status}'
            return False,f'HTTP {response.status}'
    except HTTPError as e:
        return False,f'HTTP {e.code}'
    except Exception as e:
        return False,f'{type(e).__name__}: {str(e)[:100]}'

def validate_candidate(article, now):
    errors,stats=validate_article_quality(article)
    if str(article.get('quality_version',''))!='1.5' or str(article.get('quality_status','')).upper()!='PASS':
        errors.append('Candidate chưa có QA PASS theo phiên bản 1.5')
    refs=article.get('source_references') or []
    allowed=[x.get('url') for x in refs if isinstance(x,dict)]
    primary_urls=[x.get('url') for x in refs if isinstance(x,dict) and x.get('is_primary_for_claim')]
    for ref in refs:
        if not isinstance(ref,dict):
            continue
        mode=str(ref.get('research_mode','')).upper()
        access=str(ref.get('access_status','UNVERIFIED')).upper()
        terms=str(ref.get('terms_status','UNVERIFIED')).upper()
        reuse=str(ref.get('reuse_mode','')).upper()
        if mode not in {'APPROVED_RESEARCH','LIMITED_FACTUAL_REFERENCE'}:
            errors.append(f"Nguồn thiếu chế độ nghiên cứu hợp lệ: {domain_key(ref.get('url',''))}")
        if access=='BLOCKED' or terms=='BLOCKED':
            errors.append(f"Nguồn bị chặn theo trạng thái truy cập/điều khoản: {domain_key(ref.get('url',''))}")
        if mode=='APPROVED_RESEARCH' and (access!='RESEARCH_ALLOWED' or terms!='VERIFIED'):
            errors.append(f"Nguồn được khai báo APPROVED_RESEARCH nhưng thiếu xác minh: {domain_key(ref.get('url',''))}")
        if mode=='LIMITED_FACTUAL_REFERENCE' and reuse!='FACTUAL_CITATION_ONLY':
            errors.append(f"Nguồn giới hạn chỉ được dùng dẫn chứng dữ kiện, không được tái sử dụng nội dung: {domain_key(ref.get('url',''))}")
        # Commercial-use clearance is required for reused text/media, not for citing
        # independently written factual reporting with a source link.
        if reuse!='FACTUAL_CITATION_ONLY' and str(ref.get('commercial_use_status','UNVERIFIED')).upper()!='VERIFIED':
            errors.append(f"Nội dung nguồn được tái sử dụng nhưng chưa xác minh quyền thương mại: {domain_key(ref.get('url',''))}")
    source_families={str(ref.get('url') or '').strip():ref.get('source_family') or domain_key(ref.get('url','')) for ref in refs if isinstance(ref,dict)}
    errors.extend(validate_fact_ledger_proof(
        article.get('fact_ledger'),allowed,min_claims=3,
        primary_urls=primary_urls,source_families=source_families
    ))
    count,primary,domains=source_independence(refs)
    risk=article.get('risk_level')
    if count<2 and not primary:
        errors.append('Không đủ hai miền nguồn độc lập hoặc nguồn chính thức')
    if risk=='R2' and not primary and count<3:
        errors.append('R2 thiếu nguồn chính thức hoặc ba miền nguồn độc lập')
    if risk=='R3' and not primary:
        errors.append('R3 không có nguồn chính thức')
    if risk=='R3':
        advice=validate_r3_content(article.get('title',''),article.get('body') or [])
        if advice:
            errors.append('R3 chứa lời khuyên cá nhân có thể gây hậu quả: '+', '.join(advice[:4]))
    verified=dt(article.get('verification_timestamp'))
    try:
        policy_ttl=ttl_for_data_type(article.get('data_type','general'),article.get('risk_level','R1'))
        ttl=max(1,min(policy_ttl,8760,int(article.get('freshness_ttl_hours',policy_ttl))))
    except Exception:
        ttl=24
    if not verified:
        errors.append('Thiếu verification_timestamp')
    elif now-verified>timedelta(hours=ttl):
        errors.append('Bằng chứng đã quá freshness_ttl')
    if errors:
        return False,errors,stats
    # Recheck the exact evidence sources immediately before publication. A link returning
    # HTTP 200 is not enough: the quoted evidence must still be present in the live page.
    access_results=[]
    evidence_facts=article.get('fact_ledger') or []
    evidence_urls=[]
    for fact in evidence_facts:
        if not isinstance(fact,dict):
            continue
        for proof in fact.get('evidence_verifications') or []:
            if isinstance(proof,dict):
                url=str(proof.get('source_url') or '').strip()
                if url and url not in evidence_urls:
                    evidence_urls.append(url)
    refs_by_url={str(ref.get('url') or '').strip():ref for ref in refs if isinstance(ref,dict)}
    live_pages={}
    for url in evidence_urls:
        ok,reason=check_source_access(url)
        access_results.append({'url':url,'ok':ok,'reason':reason})
        if not ok:
            errors.append(f'Nguồn không truy cập được: {domain_key(url)} ({reason})')
            continue
        ref=refs_by_url.get(url,{})
        mode=str(ref.get('research_mode') or '').upper()
        if mode not in {'APPROVED_RESEARCH','LIMITED_FACTUAL_REFERENCE'}:
            errors.append(f'Không thể tải lại chứng cứ do thiếu research_mode hợp lệ: {domain_key(url)}')
            continue
        try:
            live_pages[url]=research_pipeline.extract_page(url,access_mode=mode)
        except Exception as exc:
            errors.append(f'Không thể đọc lại nội dung chứng cứ: {domain_key(url)} ({type(exc).__name__}: {str(exc)[:100]})')
    for i,fact in enumerate(evidence_facts,1):
        if not isinstance(fact,dict):
            continue
        for item in fact.get('evidence_by_source') or []:
            if not isinstance(item,dict):
                continue
            url=str(item.get('source_url') or '').strip()
            if not url or url not in live_pages:
                continue
            snippet=normalize_evidence_text(item.get('snippet') or '')
            page=normalize_evidence_text(live_pages[url])
            if not snippet or snippet not in page:
                errors.append(f'fact_ledger[{i}] trích đoạn từ {domain_key(url)} không còn xuất hiện tại thời điểm xuất bản')
                continue
            # Vietnamese claims may localize dates/numbers differently from a
            # foreign-language source. For multilingual records, the verbatim
            # source_claim is already anchored to the exact excerpt and hashed proof.
            # Retain strict numeric comparison for legacy same-language records.
            if not str(fact.get('source_claim') or '').strip():
                claim_numbers=set(re.findall(r'\d+(?:[.,]\d+)?',str(fact.get('claim') or '')))
                snippet_numbers=set(re.findall(r'\d+(?:[.,]\d+)?',str(item.get('snippet') or '')))
                if claim_numbers and not claim_numbers.issubset(snippet_numbers):
                    errors.append(f'fact_ledger[{i}] số liệu claim không khớp trích đoạn nguồn tại thời điểm xuất bản')
    return (not errors),errors,stats|{'source_access':access_results,'independent_domains':domains,'primary_source_present':primary}

def main():
    now=datetime.now(timezone.utc)
    queue=load(QUEUE,[])
    articles=load(ARTICLES,[])
    pending=load(PENDING,[])
    seen_data=load(SEEN,{})
    if not isinstance(seen_data,dict): seen_data={'items':{}}
    seen=seen_data.setdefault('items',{})
    log=load(LOG,[])
    existing_ids={str(a.get('id')) for a in articles if a.get('id')}
    if MAX_PER_SLOT<=0:
        print('[PUBLISH] Regular article publishing disabled for this slot (digest-only slot).')
        return
    candidates=sorted(
        [x for x in queue if isinstance(x,dict) and x.get('status')=='READY'],
        key=lambda x:(x.get('prepared_at') or ''),
        reverse=True
    )
    published=[]
    for entry in candidates:
        if len(published)>=MAX_PER_SLOT:
            break
        article=entry.get('article') or {}
        ident=str(article.get('id') or entry.get('queue_id') or '')
        if not ident or ident in existing_ids:
            entry['status']='REJECT'
            entry['result_reason']='Missing or duplicate article ID'
            for item in pending:
                if item.get('article_id')==ident:
                    item['status']='REJECT'
                    item['last_error']=entry['result_reason']
            continue
        expires=dt(entry.get('expires_at'))
        if expires and expires<=now:
            entry['status']='EXPIRED'
            entry['result_reason']='Candidate freshness window expired before publication'
            for item in pending:
                if item.get('article_id')==ident:
                    item['status']='retry'
                    item['retry_after']=(now+timedelta(hours=1)).isoformat()
                    item['attempts']=0
                    item.pop('article_id',None)
            continue
        ok,errors,stats=validate_candidate(article,now)
        if not ok:
            entry['status']='HOLD'
            entry['result_reason']='; '.join(errors)[:700]
            entry['checked_at']=now.isoformat()
            entry['quality_audit']={'status':'HOLD','checked_at':now.isoformat(),'errors':errors,'stats':stats}
            for item in pending:
                if item.get('article_id')==ident:
                    item['status']='HOLD'
                    item['retry_after']=(now+timedelta(hours=24)).isoformat()
                    item['last_error']=entry['result_reason']
                    item['attempts']=0
                    item.pop('article_id',None)
            print(f"[HOLD] {article.get('title','(untitled)')}: {entry['result_reason']}")
            continue
        # Keep source/event date separate from AppNho's actual publication timestamp.
        article['appnho_published_at']=now.isoformat()
        article['published_at']=article.get('published_at') or now.isoformat()
        article['quality_status']='PASS'
        article['quality_version']='1.5'
        article['quality_audit']={'status':'PASS','checked_at':now.isoformat(),'stats':stats}
        article['publication_slot']=now.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M')
        articles.append(article)
        existing_ids.add(ident)
        published.append(article)
        usage=seen_data.setdefault('source_usage',[])
        for ref in article.get('source_references',[]):
            usage.append({'source_name':ref.get('name',''),'source_url':ref.get('url',''),
                          'category':article.get('category',''),'article_id':ident,
                          'published_at':now.isoformat(),'recorded_at':now.isoformat()})
        seen_data['source_usage']=usage[-200:]
        entry['status']='PUBLISHED'
        entry['published_at']=now.isoformat()
        entry['result_reason']='Passed final quality and source-access checks'
        for item in pending:
            if item.get('article_id')==ident:
                item['status']='published'
        for ref in article.get('source_references',[]):
            url=ref.get('url')
            if not url: continue
            record=seen.setdefault(url,{})
            record['status']='published'
            record['article_id']=ident
            record['published_at']=now.isoformat()
        print(f"[PUBLISHED] {article.get('title')} ({article.get('word_count')} words; risk={article.get('risk_level')})")
    # If no candidate passes, record a missed slot; do not downgrade thresholds or use an unverified RSS lead.
    slot_time=now.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Ho_Chi_Minh'))
    record={
        'slot':slot_time.strftime('%Y-%m-%d %H:%M'),
        'slot_kind':SLOT_KIND,
        'checked_at':now.isoformat(),
        'prepared_candidates':len(candidates),
        'published_count':len(published),
        'result':'published' if published else 'missed_slot',
        'rejected_or_held':[{'id':x.get('queue_id'),'status':x.get('status'),'reason':x.get('result_reason','')} for x in candidates if x.get('status') in {'HOLD','EXPIRED','REJECT'}][:30]
    }
    log.append(record)
    log=log[-180:]
    ARTICLES.write_text(json.dumps(articles,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    QUEUE.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    SEEN.write_text(json.dumps(seen_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    LOG.write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"[PUBLISH] Published {len(published)} candidate(s); ready queue remaining={sum(1 for x in queue if x.get('status')=='READY')}.")
    if not published:
        print('[PUBLISH] MISSED_SLOT: all available candidates failed final QA/freshness/source checks; no threshold was lowered.')

if __name__=='__main__':
    main()
