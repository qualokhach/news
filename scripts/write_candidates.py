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
    """Consume the sealed Research dossier without running a second topic gate.

    Research already fetched each page, checked topic relevance, source policy,
    independent publisher families and factual readiness. Requiring headline token
    overlap again here was a contradictory second decision point (especially for
    translated headlines and multilingual sources). Writing only checks that the
    staged source/page pairs are intact and belong to the sealed dossier.
    """
    group=item.get('group') or []
    evidence=item.get('evidence_pages') or {}
    dossier=item.get('research_dossier') or {}
    inventory=dossier.get('source_inventory') or []
    inventory_urls={str(x.get('url') or '').strip() for x in inventory if isinstance(x,dict)}
    relevant=[]
    relevant_urls=[]
    seen_urls=set()
    for source in group:
        url=str(source.get('source_url') or '').strip()
        page=evidence.get(url,'')
        if not url or not isinstance(page,str) or not page.strip():
            continue
        # New staged records carry an explicit inventory. Legacy queue entries
        # remain supported, but cannot silently add URLs absent from their dossier.
        if inventory_urls and url not in inventory_urls:
            continue
        if url not in seen_urls:
            relevant.append(source)
            relevant_urls.append(url)
            seen_urls.add(url)
    filtered_evidence={url:evidence[url] for url in relevant_urls}
    refs=[]
    inventory_by_url={str(x.get('url') or '').strip():x for x in inventory if isinstance(x,dict)}
    for source in relevant:
        url=source.get('source_url','')
        inv=inventory_by_url.get(url,{})
        info=np.source_info(url)
        refs.append({
            'url':url,
            'domain':np.domain_key(url),
            'source_family':inv.get('family') or info.get('source_family') or np.domain_key(url),
            'is_primary':bool(inv.get('is_primary',info.get('is_primary'))),
            'is_primary_for_claim':bool(inv.get('is_primary',info.get('is_primary')))
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

    def defer_writing(record, reason):
        """Keep a Research-approved candidate in Writing; never loop it back to Research."""
        attempts=int(record.get('write_attempts') or 0)+1
        record['status']='WRITING_PENDING'
        record['last_write_error']=np.clean(reason)[:500]
        record['write_attempts']=attempts
        retry_hours=min(24,max(3,2**min(attempts+1,4)))
        record['next_write_after']=(now+timedelta(hours=retry_hours)).isoformat()
        # A transient provider/formatting failure must not expire a sealed dossier.
        expiry=np.as_utc(record.get('expires_at'))
        minimum_expiry=now+timedelta(hours=72)
        if expiry is None or expiry<minimum_expiry:
            record['expires_at']=minimum_expiry.isoformat()
        return retry_hours
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
            retry=defer_writing(item,'Hồ sơ Research đã đóng nhưng thiếu cặp nguồn/trang bằng chứng trong queue; giữ nguyên hồ sơ để thử lại, không gửi ngược Research.')
            failed+=1
            print(f"[WRITING_RETRY] {item.get('lead_title')}: sealed dossier integrity check failed; retry in {retry}h.")
            continue
        if independent<2 and not has_primary:
            retry=defer_writing(item,'Hồ sơ Research đã đóng nhưng metadata source_family trong queue không còn đủ độc lập; giữ hồ sơ trong Writing để xử lý lỗi metadata.')
            failed+=1
            print(f"[WRITING_RETRY] {item.get('lead_title')}: source metadata mismatch after Research; retry in {retry}h.")
            continue
        # WRITING_PENDING is the Research hand-off contract: Research has already
        # applied its evidence-readiness gate before staging this record. Do not run
        # research_dossier_ready() again here; rebuilding/recounting facts in Writing
        # can disagree with Research (notably for multilingual or concise sources).
        # Preserve the sealed dossier verbatim; build a prompt-only dossier for legacy
        # queue records that predate the dossier field. Source/page integrity and
        # source-family checks above remain in force.
        dossier=item.get('research_dossier')
        if not isinstance(dossier,dict) or not dossier:
            dossier=np.build_research_dossier(group,evidence)
        attempted+=1
        validated={}
        def validate_for_provider(candidate,provider_label):
            candidate['_provider']=provider_label
            validated['article']=np.make_article(candidate,group,evidence)
        try:
            prompt=np.make_prompt(group,evidence,group,dossier)
            result,provider=np.generate_with_fallback(prompt,validator=validate_for_provider)
            if not result.get('publish'):
                reason=np.clean(result.get('reason','AI did not return a publishable draft'))
                raise ValueError('Writing model returned publish=false for a Research-approved dossier: '+reason[:300])
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
        except Exception as exc:
            failed+=1
            retry_hours=defer_writing(item,str(exc))
            print(f"[WRITING_RETRY] {item.get('lead_title')} (writing attempt {item.get('write_attempts')}; retry in {retry_hours}h): {exc}")
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
