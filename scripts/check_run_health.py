#!/usr/bin/env python3
"""Fail a scheduled pipeline run when the automation did not really execute."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'data/seen_items.json'
try:
    state=json.loads(p.read_text(encoding='utf-8'))
    stats=state.get('last_run_stats',{}) if isinstance(state,dict) else {}
    enabled=int(stats.get('feeds_enabled',0)); succeeded=int(stats.get('feeds_succeeded',0)); keys=int(stats.get('api_keys_configured',0)); published=int(stats.get('published',0)); failures=int(stats.get('feed_failures',0)); attempts=int(stats.get('generation_attempts',0)); responses=int(stats.get('ai_responses',0)); generation_failures=int(stats.get('generation_failures',0))
except Exception as e:
    print(f'PIPELINE HEALTH FAIL: cannot read run stats: {e}',file=sys.stderr);sys.exit(1)
print(f'PIPELINE HEALTH: feeds={succeeded}/{enabled}; api_keys_present={keys}; published={published}; feed_failures={failures}; AI attempts={attempts}; AI responses={responses}; generation_failures={generation_failures}')
if enabled<=0:
    print('PIPELINE HEALTH FAIL: no enabled feeds configured.',file=sys.stderr);sys.exit(1)
if succeeded<=0:
    print('PIPELINE HEALTH FAIL: every enabled feed failed; cursors were not advanced.',file=sys.stderr);sys.exit(1)
if keys<=0:
    print('PIPELINE HEALTH FAIL: no AI provider key is configured; no article can be generated.',file=sys.stderr);sys.exit(1)
if attempts>0 and responses==0:
    print('PIPELINE HEALTH FAIL: the pipeline attempted AI generation but received no valid provider response. Inspect provider discovery/quota/auth errors above.',file=sys.stderr);sys.exit(1)
if published==0:
    print('PIPELINE HEALTH NOTE: no article was published this run. This can be normal when no fresh story passes quality checks; inspect provider/feed warnings if repeated.')
