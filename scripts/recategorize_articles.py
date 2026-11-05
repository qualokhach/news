#!/usr/bin/env python3
"""Re-apply the deterministic section routing to every published article.

Fixes stories already live under the wrong section (for example a Vietnamese story filed as
"world"), and keeps future records consistent. Only the `category` field changes; ids, URLs,
bodies, evidence and publication dates are untouched. Safe to run on every publication.
"""
import json
from pathlib import Path
from category_resolver import resolve_category

ROOT=Path(__file__).resolve().parents[1]
FILES=[ROOT/'data/articles.json',ROOT/'data/archive_articles.json']
CATALOG=ROOT/'data/archive_catalog.json'


def urls_of(article):
    refs=[x.get('url') for x in (article.get('source_references') or []) if isinstance(x,dict)]
    return [u for u in refs if u] or list(article.get('source_urls') or [])


def recategorize(articles):
    changes=[]
    for article in articles:
        if not isinstance(article,dict) or article.get('content_type')=='news_digest':
            continue
        old=article.get('category')
        new=resolve_category(old,article.get('title'),article.get('summary'),article.get('body'),urls_of(article))
        if new!=old:
            article['category']=new
            changes.append((article.get('id'),old,new,str(article.get('title'))[:80]))
    return changes


def main():
    moved={}
    for path in FILES:
        if not path.exists(): continue
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,list): continue
        changes=recategorize(data)
        for ident,old,new,title in changes:
            moved[str(ident)]=new
            print(f'[CATEGORY] {old} -> {new}: {title}')
        if changes:
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if moved and CATALOG.exists():
        catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
        if isinstance(catalog,list):
            for entry in catalog:
                if isinstance(entry,dict) and str(entry.get('id')) in moved:
                    entry['category']=moved[str(entry.get('id'))]
            CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'[CATEGORY] Re-routed {len(moved)} article(s).')


if __name__=='__main__':
    main()
