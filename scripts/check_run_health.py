#!/usr/bin/env python3
"""Fail only when the scheduled discovery/AI execution itself did not run."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATS_PATH=ROOT/'data/seen_items.json'

def evaluate(stats):
    enabled=int(stats.get('feeds_enabled',0))
    eligible=int(stats.get('feeds_eligible',enabled))
    succeeded=int(stats.get('feeds_succeeded',0))
    keys=int(stats.get('api_keys_configured',0))
    prepared=int(stats.get('prepared',0))
    attempts=int(stats.get('generation_attempts',0))
    responses=int(stats.get('ai_responses',0))
    undated=int(stats.get('undated_items_retained',0))
    errors=[]
    notes=[]
    if enabled<=0 or eligible<=0:
        errors.append('No feeds are explicitly enabled for metadata-only discovery.')
    if succeeded<=0:
        errors.append('Every eligible discovery feed failed; no lead was collected.')
    elif eligible>0:
        feed_ratio=succeeded/eligible
        if feed_ratio<0.50:
            errors.append(
                f'Only {succeeded}/{eligible} eligible feeds succeeded ({feed_ratio:.0%}); '
                'feed coverage is below the 50% minimum operating threshold.'
            )
        elif feed_ratio<0.80:
            notes.append(
                f'Feed coverage is degraded: {succeeded}/{eligible} eligible feeds succeeded '
                f'({feed_ratio:.0%}); review failed publishers and feed audit report.'
            )
    # Research is deliberately API-free. Provider keys are required only by
    # the later writing stage, so their absence must never fail this workflow.
    if attempts>0 and keys<=0:
        errors.append('AI generation was attempted without a configured provider key.')
    if attempts>0 and responses==0:
        errors.append('AI generation was attempted but no valid provider response was received.')
    if prepared==0:
        notes.append('Discovery completed, but no candidate passed source-access/evidence/quality gates. Leads remain queued for the next research cycle; no thresholds are lowered to force publication.')
    if undated:
        notes.append(f'{undated} RSS item(s) without a valid publication date were retained outside automatic research; they will be reconsidered if the feed later supplies a date.')
    return errors,notes

def main():
    try:
        state=json.loads(STATS_PATH.read_text(encoding='utf-8'))
        stats=state.get('last_run_stats',{}) if isinstance(state,dict) else {}
    except Exception as exc:
        print(f'PIPELINE HEALTH FAIL: cannot read run stats: {exc}',file=sys.stderr)
        return 1
    enabled=int(stats.get('feeds_enabled',0)); eligible=int(stats.get('feeds_eligible',enabled))
    succeeded=int(stats.get('feeds_succeeded',0)); keys=int(stats.get('api_keys_configured',0))
    prepared=int(stats.get('prepared',0)); attempts=int(stats.get('generation_attempts',0))
    responses=int(stats.get('ai_responses',0)); failures=int(stats.get('feed_failures',0))
    gen_failures=int(stats.get('generation_failures',0))
    undated=int(stats.get('undated_items_retained',0))
    print(f'PIPELINE HEALTH: feeds={succeeded}/{eligible} eligible ({enabled} enabled); API keys (writing stage only)={keys}; prepared={prepared}; AI attempts={attempts}; responses={responses}; feed failures={failures}; generation failures={gen_failures}')
    errors,notes=evaluate(stats)
    for item in errors: print('PIPELINE HEALTH FAIL: '+item,file=sys.stderr)
    for item in notes: print('PIPELINE HEALTH NOTE: '+item)
    return 1 if errors else 0

if __name__=='__main__':
    raise SystemExit(main())
