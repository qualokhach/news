#!/usr/bin/env python3
"""Write evidence-backed candidates staged by the API-free research workflow."""
import json, os, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import news_pipeline as np

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/'data/research_queue.json'
PENDING=ROOT/'data/pending.json'
ARTICLES=ROOT/'data/articles.json'
ARCHIVE=ROOT/'data/archive_articles.json'
SEEN=ROOT/'data/seen_items.json'
MAX_WRITE=max(1,int(os.getenv('MAX_ARTICLES_PER_SLOT') or '3'))


def _filter_candidate_evidence(item):
    """Drop unrelated headlines/evidence before spending any model calls."""
    group=item.get('group') or []
    evidence=item.get('evidence_pages') or {}
    lead=(item.get('lead_title') or
          (group[0].get('discovery_title','') if group else '')).strip()
    relevant=[]
    relevant_urls=[]
    seen_urls=set()
    for source in group:
        title=source.get('discovery_title','')
        # A related publisher headline must share meaningful terms and a
        # modest title-similarity score with the staged lead.
        if np.headlines_related(lead,title):
            url=source.get('source_url','')
            page=evidence.get(url,'')
            # A source must match both its own headline and the candidate's
            # anchor topic. This blocks unrelated pages accidentally carried
            # into a previously grouped discovery record.
            if (url and isinstance(page,str) and bool(page.strip())
                    and np.evidence_matches_title(lead,page)
                    and np.evidence_matches_title(title,page)):
                relevant.append(source)
                if url not in seen_urls:
                    relevant_urls.append(url)
                    seen_urls.add(url)
    filtered_evidence={url:evidence[url] for url in relevant_urls}
    refs=[]
    for source in relevant:
        info=np.source_info(source.get('source_url',''))
        refs.append({
            'url':source.get('source_url',''),
            'domain':np.domain_key(source.get('source_url','')),
            'source_family':info.get('source_family') or np.domain_key(source.get('source_url','')),
            'is_primary':bool(info.get('is_primary')),
            'is_primary_for_claim':bool(info.get('is_primary'))
        })
    independent,has_primary,_=np.source_independence(refs)
    item['group']=relevant
    item['evidence_pages']=filtered_evidence
    item['source_urls']=list(relevant_urls)
    return relevant,filtered_evidence,independent,has_primary


def main():
    queue=json.loads(QUEUE.read_text(encoding='utf-8')) if QUEUE.exists() else []
    active=json.loads(ARTICLES.read_text(encoding='utf-8')) if ARTICLES.exists() else []
    archived=json.loads(ARCHIVE.read_text(encoding='utf-8')) if ARCHIVE.exists() else []
    seen_data=json.loads(SEEN.read_text(encoding='utf-8')) if SEEN.exists() else {'items':{}}
    pending=json.loads(PENDING.read_text(encoding='utf-8')) if PENDING.exists() else []
    seen=seen_data.setdefault('items',{})
    known=active+archived+[x.get('article',{}) for x in queue if isinstance(x,dict) and isinstance(x.get('article'),dict)]
    now=datetime.now(timezone.utc); now_iso=now.isoformat()

    def return_to_research(record, reason):
        # A thin dossier is a research task, not a terminal writing failure.
        record['status']='RESEARCH_PENDING'
        record['editorial_reason']=np.clean(reason)[:500]
        record['research_retry_after']=(now+timedelta(hours=3)).isoformat()
        restored=0
        for lead in record.get('discovery_group') or record.get('group') or []:
            url=np.canon(lead.get('source_url',''))
            if not url:
                continue
            existing=next((x for x in pending if np.canon(x.get('source_url',''))==url),None)
            if existing:
                existing['status']='retry'
                existing['retry_after']=(now+timedelta(hours=3)).isoformat()
                existing['last_error']='Writing preflight requested more evidence: '+np.clean(reason)[:240]
                existing['research_request']=np.clean(reason)[:180]
            else:
                copy=dict(lead)
                copy['status']='retry'
                copy['retry_after']=(now+timedelta(hours=3)).isoformat()
                copy['attempts']=int(copy.get('attempts') or 0)
                copy['last_error']='Writing preflight requested more evidence: '+np.clean(reason)[:240]
                copy['research_request']=np.clean(reason)[:180]
                pending.append(copy)
            if url in seen:
                seen[url]['status']='research_pending'
            restored+=1
        record['research_requeued_sources']=restored
        return restored
    def write_is_due(record):
        retry_at=np.as_utc(record.get('next_write_after'))
        return retry_at is None or retry_at<=now
    staged=[x for x in queue if isinstance(x,dict) and x.get('status')=='WRITING_PENDING'
            and write_is_due(x)]
    staged.sort(key=lambda x:x.get('staged_at',''))
    if not staged:
        print('[WRITING] No due WRITING_PENDING candidates; AI providers were not called.')
        return
    if not any(os.getenv(k,'').strip() for k in ('GEMINI_API_KEY','CLOUDFLARE_API_TOKEN','OPENROUTER_API_KEY')):
        raise SystemExit('ERROR: Writing stage has candidates but no AI provider key is configured.')
    written=0; failed=0; attempted=0
    for item in staged:
        # Cap actual model-attempted candidates, not successful publications.
        # Otherwise a run with repeated failures could consume API calls on the entire queue.
        if attempted>=MAX_WRITE: break
        expiry=np.as_utc(item.get('expires_at'))
        if expiry and expiry<now:
            item['status']='EXPIRED'
            continue
        group,evidence,independent,has_primary=_filter_candidate_evidence(item)
        if not group or not evidence:
            restored=return_to_research(item,'Không còn nguồn có bằng chứng trang hợp lệ sau khi lọc tiêu đề không liên quan.')
            print(f"[RESEARCH_MORE] {item.get('lead_title')}: no relevant source evidence; restored {restored} source lead(s); skipped AI calls.")
            continue
        if independent<2 and not has_primary:
            restored=return_to_research(item,'Sau khi loại nguồn thuộc sự kiện khác, còn dưới hai nguồn độc lập và không có nguồn chính thức.')
            print(f"[RESEARCH_MORE] {item.get('lead_title')}: insufficient independent sources; restored {restored} source lead(s); skipped AI calls.")
            continue
        dossier=item.get('research_dossier') or np.build_research_dossier(group,evidence)
        dossier_ok,dossier_reason=np.research_dossier_ready(dossier)
        if not dossier_ok:
            restored=return_to_research(item,dossier_reason)
            print(f"[RESEARCH_MORE] {item.get('lead_title')}: {dossier_reason}; restored {restored} source lead(s); no AI calls.")
            continue
        attempted+=1
        validated={}
        def validate_for_provider(candidate,provider_label):
            candidate['_provider']=provider_label
            validated['article']=np.make_article(candidate,group,evidence)
        try:
            prompt=np.make_prompt(group,evidence,group,dossier)
            result,provider=np.generate_with_fallback(prompt,validator=validate_for_provider)
            if not result.get('publish'):
                reason=np.clean(result.get('reason','Not enough verified evidence'))
                restored=return_to_research(item,reason)
                print(f"[RESEARCH_MORE] {item.get('lead_title')}: writer identified a missing evidence detail; restored {restored} source lead(s).")
                continue
            result['_provider']=provider
            article=validated.get('article')
            if not article:
                raise ValueError('AI output failed article validation')
            article['origin']='auto'
            image=np.find_licensed_image(article)
            if image:
                article['content_image_url']=image['url']
                article['content_image_alt']=image['alt']
                article['content_image_credit']=image['credit']+' ('+image['license']+')'
                article['content_image_credit_url']=image['credit_url']
                article['content_image_license_url']=image['license_url']
            duplicate=any(np.similarity(article.get('title',''),a.get('title',''))>0.70 for a in known)
            duplicate_body=any(np.similarity(' '.join(article.get('body') or []),' '.join(a.get('body') or []))>0.66 for a in known if a.get('body'))
            if duplicate or duplicate_body or any(str(a.get('id'))==str(article.get('id')) for a in known):
                item['status']='REJECT'
                item['editorial_reason']='Duplicate title, body, or article ID'
                continue
            ttl=int(article.get('freshness_ttl_hours',24))
            queue.append({'queue_id':article['id'],'status':'READY','prepared_at':now_iso,
                          'expires_at':(now+timedelta(hours=ttl)).isoformat(),
                          'source_urls':article.get('source_urls',[]),'article':article})
            item['status']='WRITTEN'
            item['written_article_id']=article['id']
            item.pop('last_write_error',None)
            item.pop('next_write_after',None)
            for lead in group:
                u=np.canon(lead.get('source_url',''))
                if u:
                    seen.setdefault(u,{})['status']='ready_for_publish'
                    seen[u]['article_id']=article['id']
            known.append(article); written+=1
            print(f"[READY] {article.get('title')} ({article.get('word_count')} words; provider={provider})")
            time.sleep(0.5)
        except np.EditorialEvidenceGateError as exc:
            item['last_write_error']=np.clean(str(exc))[:500]
            restored=return_to_research(item,str(exc))
            print(f"[RESEARCH_MORE] {item.get('lead_title')}: evidence gate identified missing proof; restored {restored} source lead(s); no further provider calls.")
        except Exception as exc:
            failed+=1
            item['last_write_error']=str(exc)[:500]
            attempts=int(item.get('write_attempts') or 0)+1
            item['write_attempts']=attempts
            item['status']='WRITING_PENDING'
            retry_hours=min(24,max(3,2**min(attempts+1,4)))
            item['next_write_after']=(now+timedelta(hours=retry_hours)).isoformat()
            print(f"[WARN] Writing failed for {item.get('lead_title')} (technical attempt {attempts}; retry in {retry_hours}h): {exc}")
    QUEUE.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    SEEN.write_text(json.dumps(seen_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ready=sum(1 for x in queue if isinstance(x,dict) and x.get('status')=='READY')
    remaining=sum(1 for x in queue if isinstance(x,dict) and x.get('status')=='WRITING_PENDING')
    no_article_failure=(written==0 and failed>0)
    print(f"[WRITING] attempted={attempted} written={written} failed={failed} ready_queue={ready} staged_remaining={remaining}")
    # Keep queue and research-feedback changes committed. Only technical provider/
    # runtime failures set no_article_failure; evidence gaps return to Research.
    output_path=os.getenv('GITHUB_OUTPUT','').strip()
    if output_path:
        with open(output_path,'a',encoding='utf-8') as handle:
            handle.write(f"written={written}\nfailed={failed}\nno_article_failure={str(no_article_failure).lower()}\n")

if __name__=='__main__':
    main()
