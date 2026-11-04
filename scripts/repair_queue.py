#!/usr/bin/env python3
"""Keep data/research_queue.json internally consistent before every audit.

One READY candidate that the audit would reject used to make *every* later workflow
(research, writing, publishing) fail at its first audit step, so nothing was published.
This script re-applies the shared READY gate. A candidate that fails is repaired when the
sealed source pages still exist in its staging record, otherwise it is withdrawn from READY
and sent back to WRITING_PENDING for a rewrite. It never lowers any quality threshold.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from content_quality import compute_verified_numbers, ready_candidate_errors

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/'data/research_queue.json'


def repair(queue, now=None):
    """Mutates queue in place; returns (repaired_ids, withdrawn_ids)."""
    now=now or datetime.now(timezone.utc)
    staged_by_article={str(x.get('written_article_id')):x for x in queue
                       if isinstance(x,dict) and x.get('written_article_id')}
    repaired=[]; withdrawn=[]
    for entry in queue:
        if not isinstance(entry,dict) or entry.get('status')!='READY':
            continue
        article=entry.get('article')
        errors=ready_candidate_errors(article) if isinstance(article,dict) else ['READY entry has no article']
        if not errors:
            continue
        ident=str((article or {}).get('id') or entry.get('queue_id') or '')
        staged=staged_by_article.get(ident)
        if staged and isinstance(article,dict) and isinstance(staged.get('evidence_pages'),dict):
            # Records written before verified_numbers existed: recompute from the sealed pages.
            article['verified_numbers']=compute_verified_numbers(
                article.get('body') or [],article.get('fact_ledger') or [],staged['evidence_pages'])
            if not ready_candidate_errors(article):
                repaired.append(ident); continue
        entry['status']='REJECT'
        entry['result_reason']=('Withdrawn before audit: '+'; '.join(errors))[:700]
        withdrawn.append(ident)
        if staged and staged.get('status')=='WRITTEN':
            staged['status']='WRITING_PENDING'
            staged.pop('written_article_id',None)
            staged.pop('next_write_after',None)
            staged['last_write_error']=('Bản viết trước không qua kiểm định: '+'; '.join(errors))[:500]
            staged['write_attempts']=int(staged.get('write_attempts') or 0)+1
    return repaired,withdrawn


def main():
    if not QUEUE.exists():
        print('[REPAIR] No research queue file; nothing to repair.'); return
    queue=json.loads(QUEUE.read_text(encoding='utf-8'))
    if not isinstance(queue,list):
        raise SystemExit('ERROR: research queue must be a JSON array')
    repaired,withdrawn=repair(queue)
    if repaired or withdrawn:
        QUEUE.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'[REPAIR] repaired={len(repaired)} withdrawn={len(withdrawn)}')
    for x in repaired: print('  repaired:',x)
    for x in withdrawn: print('  withdrawn:',x)


if __name__=='__main__':
    main()
