#!/usr/bin/env python3
"""Deterministic pre/post-flight checks for AppNho News data and navigation."""
import json, re, sys
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
ROOT=Path(__file__).resolve().parents[1]
CATEGORIES={"world","vietnam","sports","technology"}
def read_json(path, default=None):
    p=ROOT/path
    if not p.exists():
        if default is not None: return default
        raise AssertionError(f"Missing required file: {path}")
    return json.loads(p.read_text(encoding="utf-8"))
class AnchorParser(HTMLParser):
    def __init__(self): super().__init__(); self.hrefs=[]; self.ids=set()
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if values.get("href") is not None: self.hrefs.append(values["href"])
        if values.get("id"): self.ids.add(values["id"])

def audit_internal_links():
    html_files=list(ROOT.glob("*.html"))
    parsed={p.name:AnchorParser() for p in html_files}
    for name,parser in parsed.items(): parser.feed((ROOT/name).read_text(encoding="utf-8"))
    errors=[]
    for name,parser in parsed.items():
        for href in parser.hrefs:
            if not href or href.startswith(("https://","http://","mailto:","tel:","javascript:")): continue
            parts=urlsplit(href)
            if parts.path in ("","./"): target=ROOT/"index.html"
            else: target=(ROOT/unquote(parts.path)).resolve()
            try: target.relative_to(ROOT.resolve())
            except ValueError: errors.append(f"{name}: path escapes repo: {href}"); continue
            if not target.is_file(): errors.append(f"{name}: missing local target: {href}"); continue
            if parts.fragment:
                target_name=target.name
                if target_name in parsed and unquote(parts.fragment) not in parsed[target_name].ids:
                    errors.append(f"{name}: missing fragment target: {href}")
    assert not errors, "Internal link audit failed:\n"+"\n".join(errors[:30])
    print(f"LINK AUDIT PASS: checked {sum(len(p.hrefs) for p in parsed.values())} local/external anchors across {len(parsed)} HTML pages")

GA_ID="G-K9C4KKZPEE"
def audit_shell_and_analytics():
    """Every public page must carry the shared AppNho header/footer and the GA4 tag (G-K9C4KKZPEE).
    Articles (including auto-published ones) are rendered by article.html?id=<id>, so covering the HTML pages covers all articles."""
    errors=[]
    for p in sorted(ROOT.glob("*.html")):
        text=p.read_text(encoding="utf-8")
        if GA_ID not in text: errors.append(f"{p.name}: missing GA4 tag {GA_ID}")
        if "APPNHO-SHELL:HEADER:START" not in text: errors.append(f"{p.name}: missing shared AppNho header")
        if "APPNHO-SHELL:FOOTER:START" not in text: errors.append(f"{p.name}: missing shared AppNho footer")
    assert not errors, "Shared header/footer/analytics audit failed:\n"+"\n".join(errors)
    print(f"SHELL+GA4 AUDIT PASS: {len(list(ROOT.glob('*.html')))} HTML pages")

def main():
    required=["index.html","article.html","about.html","assets/app.js","assets/article.js","assets/style.css",".github/workflows/build-news.yml"]
    for name in required:
        assert (ROOT/name).is_file(), f"Missing required file: {name}"
    active=read_json("data/articles.json")
    catalog=read_json("data/archive_catalog.json",[])
    pending=read_json("data/pending.json",[])
    manifest=read_json("data/archive_manifest.json",["data/archive_articles.json"])
    assert isinstance(active,list), "data/articles.json must be a JSON array"
    assert isinstance(catalog,list), "archive catalog must be a JSON array"
    assert isinstance(pending,list), "pending queue must be a JSON array"
    assert isinstance(manifest,list), "archive manifest must be a JSON array"
    archive_paths={"data/archive_articles.json"}
    for item in manifest:
        assert isinstance(item,str) and item.startswith("data/archive") and item.endswith(".json"), f"Unsafe archive manifest path: {item!r}"
        assert (ROOT/item).is_file(), f"Manifest archive file missing: {item}"
        archive_paths.add(item)
    for item in catalog:
        path=item.get("file")
        if path:
            assert path.startswith("data/archive") and path.endswith(".json"), f"Unsafe catalog archive path: {path}"
            assert (ROOT/path).is_file(), f"Catalog points to missing archive file: {path}"
            archive_paths.add(path)
    archive=[]
    for path in sorted(archive_paths):
        batch=read_json(path)
        assert isinstance(batch,list), f"Archive batch must be array: {path}"
        archive.extend(batch)
    def check_articles(items,label):
        ids=[]
        for a in items:
            assert isinstance(a,dict) and a.get("id"), f"{label} contains record without ID"
            ids.append(str(a["id"]))
            assert a.get("category") in CATEGORIES, f"Invalid category in {label}: {a.get('id')} / {a.get('category')}"
            assert a.get("title"), f"Missing title in {label}: {a.get('id')}"
        assert len(ids)==len(set(ids)), f"Duplicate IDs inside {label}"
        return set(ids)
    active_ids=check_articles(active,"active articles")
    archive_ids=check_articles(archive,"archive batches")
    assert not (active_ids & archive_ids), f"Active/archive IDs overlap: {sorted(active_ids & archive_ids)[:5]}"
    catalog_ids={str(x.get("id")) for x in catalog if x.get("id")}
    # Catalog can index archived article IDs only; every catalog entry must resolve to a full body.
    all_archive_ids=set(str(x.get("id")) for x in archive if x.get("id"))
    assert catalog_ids <= all_archive_ids, f"Catalog entries without article bodies: {sorted(catalog_ids-all_archive_ids)[:5]}"
    all_categories={a.get("category") for a in active+archive}
    missing=CATEGORIES-all_categories
    assert not missing, f"No published or archived articles in categories: {sorted(missing)}"
    html=(ROOT/"index.html").read_text(encoding="utf-8")
    js=(ROOT/"assets/app.js").read_text(encoding="utf-8")
    for cat in sorted(CATEGORIES):
        assert f"?category={cat}" in html, f"Homepage category link missing: {cat}"
        assert cat in js, f"Frontend category handling missing: {cat}"
    assert "data/archive_manifest.json" in js, "Homepage does not load archive manifest"
    assert 'categoryHeroTitle' in js and 'categoryMoreNav' in js, "Category indexes must have a personalized hero and onward navigation"
    assert 'href="./#archive"' in js, "Category onward navigation must link to the history section"
    assert '.category-hero' in (ROOT/"assets/style.css").read_text(encoding="utf-8"), "Category hero styling is missing"
    article_js=(ROOT/"assets/article.js").read_text(encoding="utf-8")
    assert "data/archive_manifest.json" in article_js, "Article page does not load archive manifest"
    audit_shell_and_analytics()
    audit_internal_links()
    workflow=(ROOT/".github/workflows/build-news.yml").read_text(encoding="utf-8")
    assert "schedule:" in workflow and 'cron: "0 23,10 * * *"' in workflow, "Expected twice-daily VN schedule missing"
    print(f"SITE AUDIT PASS: active={len(active)} archived={len(archive)} catalog={len(catalog)} pending={len(pending)} archive_files={len(archive_paths)} categories={','.join(sorted(all_categories))}")
if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"SITE AUDIT FAIL: {e}",file=sys.stderr); sys.exit(1)
