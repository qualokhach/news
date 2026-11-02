#!/usr/bin/env python3
"""Write evidence-backed candidates staged by the API-free research workflow."""
import json, os, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import news_pipeline as np

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/'data/research_queue.json'
ARTICLES=ROOT/'data/articles.json'
ARCHIVE=ROOT/'data/archive_articles.json'
SEEN=ROOT/'data/seen_items.json'
MAX_WRITE=max(1,int(os.getenv('MAX_ARTICLES_PER_SLOT') or '3'))

def main():
    queue=json.loads(QUEUE.read_text(encoding='utf-8')) if QUEUE.exists() else []
    active=json.loads(ARTICLES.read_text(encoding='utf-8')) if ARTICLES.exists() else []
    archived=json.loads(ARCHIVE.read_text(encoding='utf-8')) if ARCHIVE.exists() else []
    seen_data=json.loads(SEEN.read_text(encoding='utf-8')) if SEEN.exists() else {'items':{}}
    seen=seen_data.setdefault('items',{})
    known=active+archived+[x.get('article',{}) for x in queue if isinstance(x,dict) and isinstance(x.get('article'),dict)]
    now=datetime.now(timezone.utc); now_iso=now.isoformat()
    staged=[x for x in queue if isinstance(x,dict) and x.get('status')=='WRITING_PENDING']
    staged.sort(key=lambda x:x.get('staged_at',''))
    if not staged:
        print('[WRITING] No WRITING_PENDING candidates; AI providers were not called.')
        return
    if not any(os.getenv(k,'').strip() for k in ('GEMINI_API_KEY','XAI_API_KEY','OPENROUTER_API_KEY')):
        raise SystemExit('ERROR: Writing stage has candidates but no AI provider key is configured.')
    written=0; failed=0
    for item in staged:
        if written>=MAX_WRITE: break
        expiry=np.as_utc(item.get('expires_at'))
        if expiry and expiry<now:
            item['status']='EXPIRED'
            continue
        group=item.get('group') or []
        evidence=item.get('evidence_pages') or {}
        if not group or not evidence:
            item['status']='HOLD'
            item['editorial_reason']='Missing staged source evidence'
            continue
        try:
            result,provider=np.generate_with_fallback(np.make_prompt(group,evidence,item.get('discovery_group') or group))
            if not result.get('publish'):
                item['status']='HOLD'
                item['editorial_reason']=np.clean(result.get('reason','Not enough verified evidence'))[:300]
                print(f"[HOLD] {item.get('lead_title')}: {item['editorial_reason']}")
                continue
            result['_provider']=provider
            article=np.make_article(result,group,evidence)
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
            item['last_write_error']=str(exc)[:500]
            print(f"[WARN] Writing failed for {item.get('lead_title')}: {exc}")
    QUEUE.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    SEEN.write_text(json.dumps(seen_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ready=sum(1 for x in queue if isinstance(x,dict) and x.get('status')=='READY')
    remaining=sum(1 for x in queue if isinstance(x,dict) and x.get('status')=='WRITING_PENDING')
    no_article_failure=(written==0 and failed>0)
    print(f"[WRITING] written={written} failed={failed} ready_queue={ready} staged_remaining={remaining}")
    # Keep the queue changes committed, then let the workflow mark the run failed
    # if every attempted draft failed technically. Editorial HOLDs remain a valid
    # no-publication outcome and do not trigger this flag.
    output_path=os.getenv('GITHUB_OUTPUT','').strip()
    if output_path:
        with open(output_path,'a',encoding='utf-8') as handle:
            handle.write(f"written={written}\nfailed={failed}\nno_article_failure={str(no_article_failure).lower()}\n")

if __name__=='__main__':
    main()
