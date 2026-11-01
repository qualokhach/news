#!/usr/bin/env python3
"""Check configured feed endpoints without stopping the news pipeline on individual failures."""
import concurrent.futures, json, sys, urllib.request, urllib.error
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
FEEDS=ROOT/'config/feeds.json'
REPORT=ROOT/'data/feed_health.json'
UA='AppNhoNewsBot/1.0 (+https://github.com/qualokhach/news)'

def robots_allowed(url):
    parts=urlsplit(url)
    robots_url=f'{parts.scheme}://{parts.netloc}/robots.txt'
    parser=RobotFileParser()
    parser.set_url(robots_url)
    try:
        req=urllib.request.Request(robots_url,headers={'User-Agent':UA})
        with urllib.request.urlopen(req,timeout=5) as response:
            parser.parse(response.read(256_000).decode('utf-8','replace').splitlines())
        return parser.can_fetch(UA,url)
    except urllib.error.HTTPError as e:
        if e.code==404:
            parser.parse([])
            return True
        return False
    except Exception:
        return False

def check(feed):
    result={'name':feed.get('name','?'),'url':feed.get('url',''),'category':feed.get('category',''),'enabled':bool(feed.get('enabled')),'checked_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    if not feed.get('enabled'):
        result.update(status='disabled',items=0,detail='Disabled in config')
        return result
    discovery_status=str(feed.get('discovery_access_status','UNVERIFIED')).upper()
    feed_mode=str(feed.get('status','')).lower()
    if discovery_status not in {'DISCOVERY_ALLOWED','DISCOVERY_ONLY'} or feed_mode not in {'discovery_only','discovery_allowed'}:
        result.update(status='not_authorized_for_discovery',items=0,detail='Feed is not explicitly configured for metadata-only discovery')
        return result
    result['mode']='metadata_only'
    try:
        if not robots_allowed(feed['url']):
            result.update(status='robots_blocked',items=0,detail='robots.txt disallows feed access or could not be verified')
            return result
        req=urllib.request.Request(feed['url'],headers={'User-Agent':UA,'Accept':'application/rss+xml, application/atom+xml, application/xml, text/xml,*/*;q=0.5'})
        with urllib.request.urlopen(req,timeout=7) as r:
            result['http_status']=r.status
            raw=r.read(1_000_000)
        root=ET.fromstring(raw)
        atom='{http://www.w3.org/2005/Atom}'
        items=root.findall('.//item') or root.findall(f'.//{atom}entry')
        if not items:
            result.update(status='invalid_feed',items=0,detail='HTTP success but no RSS item/Atom entry elements')
        else:
            result.update(status='metadata_only_ok',items=len(items),detail='RSS/Atom parsed; only title, URL and publication date may be retained')
    except urllib.error.HTTPError as e:
        result.update(status='http_error',http_status=e.code,items=0,detail=f'HTTP {e.code}')
    except Exception as e:
        result.update(status='error',items=0,detail=f'{type(e).__name__}: {str(e)[:180]}')
    return result

def main():
    feeds=json.loads(FEEDS.read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(check,feeds))
    counts={}
    for r in results:
        c=counts.setdefault(r['category'],{'configured':0,'enabled':0,'ok':0,'failed':0})
        c['configured']+=1; c['enabled']+=int(r['enabled'])
        if r['status']=='metadata_only_ok': c['ok']+=1
        elif r['enabled']: c['failed']+=1
        print(f"[{r['status'].upper()}] {r['category']} | {r['name']} | {r.get('http_status','-')} | items={r['items']} | {r['detail']}")
    REPORT.write_text(json.dumps({'checked_at':results[0]['checked_at'] if results else None,'summary':counts,'feeds':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ok=sum(r['status']=='metadata_only_ok' for r in results); enabled=sum(r['enabled'] and r.get('mode')=='metadata_only' for r in results)
    print(f'FEED_AUDIT_SUMMARY: {ok}/{enabled} enabled feeds healthy; report={REPORT.relative_to(ROOT)}')
    # Audit is diagnostic; one broken publisher must never block all collection.
if __name__=='__main__': main()
