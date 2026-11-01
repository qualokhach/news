#!/usr/bin/env python3
"""Deterministic pre/post-flight checks for AppNho News data and navigation."""
import json, re, sys, csv
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
from content_quality import validate_article_quality, validate_fact_ledger_proof, source_independence, domain_key
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
    required=["index.html","article.html","about.html","assets/app.js","assets/article.js","assets/style.css",
              ".github/workflows/build-news.yml",".github/workflows/research-news.yml",
              ".github/workflows/legacy-upgrade.yml",".github/workflows/validate-news.yml",
              "data/research_queue.json","config/source_directory.csv","social_metadata.json","feed.xml","sitemap.xml","scripts/publish_ready.py",
              "scripts/upgrade_legacy_articles.py","scripts/content_quality.py","scripts/resolve_publish_slot.py",
              "reports/legacy_article_audit_initial.csv","reports/legacy_article_audit_initial.json"]
    for name in required:
        assert (ROOT/name).is_file(), f"Missing required file: {name}"
    active=read_json("data/articles.json")
    catalog=read_json("data/archive_catalog.json",[])
    pending=read_json("data/pending.json",[])
    research_queue=read_json("data/research_queue.json",[])
    manifest=read_json("data/archive_manifest.json",["data/archive_articles.json"])
    assert isinstance(research_queue,list), "research queue must be a JSON array"
    ready_ids=set()
    for entry in research_queue:
        assert isinstance(entry,dict), "research queue contains a non-object entry"
        if entry.get("status")=="READY":
            article=entry.get("article")
            assert isinstance(article,dict) and article.get("id"), "READY candidate has no article ID"
            assert article.get("quality_version")=="1.5" and article.get("quality_status")=="PASS", f"READY candidate not v1.5 PASS: {entry.get('queue_id')}"
            errors,_=validate_article_quality(article)
            assert not errors, f"READY candidate failed quality gate: {entry.get('queue_id')}: {errors}"
            refs=article.get("source_references") or []
            urls=[x.get("url") for x in refs if isinstance(x,dict)]
            primary_urls=[x.get("url") for x in refs if isinstance(x,dict) and x.get("is_primary")]
            source_families={str(ref.get("url") or "").strip():ref.get("source_family") or domain_key(ref.get("url","")) for ref in refs if isinstance(ref,dict)}
            ledger_errors=validate_fact_ledger_proof(article.get("fact_ledger"),urls,min_claims=3,primary_urls=primary_urls,source_families=source_families)
            assert not ledger_errors, f"READY candidate has invalid fact ledger: {entry.get('queue_id')}: {ledger_errors}"
            count,primary,_=source_independence(refs)
            assert count>=2 or primary, f"READY candidate lacks independent sources: {entry.get('queue_id')}"
            assert entry.get("queue_id") not in ready_ids, f"Duplicate READY queue ID: {entry.get('queue_id')}"
            ready_ids.add(entry.get("queue_id"))
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
    all_articles_by_id={str(a.get("id")):a for a in active+archive if a.get("id")}
    for article in active+archive:
        assert article.get("appnho_published_at") or article.get("fetched_at"), f"Missing AppNho publication date: {article.get('id')}"
        assert "editorial_note" not in article, f"Internal editorial note still present in public record: {article.get('id')}"
    social=read_json("social_metadata.json",{})
    assert isinstance(social,dict), "social_metadata.json must be an object"
    for ident,article in all_articles_by_id.items():
        share_file=ROOT/"share"/ident/"index.html"
        assert share_file.is_file(), f"Missing static share preview for article {ident}"
        share_html=share_file.read_text(encoding="utf-8")
        assert 'property="og:image"' in share_html and 'property="og:title"' in share_html, f"Share preview missing Open Graph tags: {ident}"
        assert ident in social, f"Social metadata missing article ID: {ident}"
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
    research_workflow=(ROOT/".github/workflows/research-news.yml").read_text(encoding="utf-8")
    legacy_workflow=(ROOT/".github/workflows/legacy-upgrade.yml").read_text(encoding="utf-8")
    validate_workflow=(ROOT/".github/workflows/validate-news.yml").read_text(encoding="utf-8")
    assert all(f'cron: "{cron}"' in workflow for cron in ("45 22 * * *", "45 4 * * *", "45 9 * * *")), "Finalization must use three separately identifiable Vietnam publication slots."
    assert "scripts/resolve_publish_slot.py" in workflow and "steps.slot.outputs.slot_kind" in workflow, "Publication workflow must use the tested slot resolver."
    assert all(cron in research_workflow for cron in (
        'cron: "45 21 * * *"', 'cron: "45 3 * * *"', 'cron: "45 8 * * *"'
    )), "Research queue schedule must precede all three Vietnam publication slots."
    assert 'NEWS_PUBLIC_FACTUAL_RESEARCH: "1"' in research_workflow, "Scheduled research must enable limited factual-reference mode."
    assert 'MAX_OPENROUTER_CALLS_PER_RUN: "8"' in research_workflow, "OpenRouter free-tier call cap missing."
    assert 'workflow_dispatch:' in legacy_workflow and 'schedule:' not in legacy_workflow, "Legacy upgrades must be manual-only to protect already-published articles."
    assert 'LEGACY_UPGRADE_APPLY: ${{ inputs.apply }}' in legacy_workflow, "Legacy upgrade must require an explicit apply input."
    legacy_script=(ROOT/"scripts/upgrade_legacy_articles.py").read_text(encoding="utf-8")
    assert "LEGACY_UPGRADE_APPLY" in legacy_script, "Legacy upgrade script must default to dry-run."
    feeds=json.loads((ROOT/"config/feeds.json").read_text(encoding="utf-8"))
    assert len(feeds)>=40 and all(f.get("enabled") and f.get("status")=="discovery_only" and f.get("discovery_access_status")=="DISCOVERY_ONLY" for f in feeds), "At least 40 enabled metadata-only RSS feeds are required for automated discovery."
    with (ROOT/"config/source_directory.csv").open(encoding="utf-8-sig",newline="") as fh:
        source_rows=list(csv.DictReader(fh,delimiter=";"))
    required_source_fields={"source_family","access_status","terms_status","terms_url","robots_url","allowed_fields","commercial_use_status","rate_limit","quota","attribution_rule","last_checked","license_notes","claim_role"}
    assert source_rows and required_source_fields.issubset(set(source_rows[0])), "Source directory schema is incomplete."
    for row in source_rows:
        access=(row.get("access_status") or "UNVERIFIED").upper()
        terms=(row.get("terms_status") or "UNVERIFIED").upper()
        commercial=(row.get("commercial_use_status") or "UNVERIFIED").upper()
        assert access in {"UNVERIFIED","RESEARCH_ALLOWED","BLOCKED"}, f"Invalid source access status: {access}"
        assert terms in {"UNVERIFIED","VERIFIED","BLOCKED"}, f"Invalid source terms status: {terms}"
        assert commercial in {"UNVERIFIED","VERIFIED","NOT_ALLOWED"}, f"Invalid commercial-use status: {commercial}"
        if access=="RESEARCH_ALLOWED":
            assert terms=="VERIFIED" and row.get("terms_url"), f"Research-enabled source lacks verified terms URL: {row.get('ID')}"
        if commercial=="VERIFIED":
            assert access=="RESEARCH_ALLOWED" and terms=="VERIFIED" and row.get("allowed_fields"), f"Commercial source lacks verified access/allowed fields: {row.get('ID')}"
    assert "on:" in validate_workflow and "push:" in validate_workflow, "Push validation workflow missing."
    assert not re.search(r"^\s*push:",workflow,re.M), "Publishing workflow must not publish immediately on code pushes."
    article_js=(ROOT/"assets/article.js").read_text(encoding="utf-8")
    assert 'article-byline' in article_js and '"name":"AppNho"' in article_js, "Article page must show AppNho byline."
    assert 'appnho_published_at' in article_js, "Article page must distinguish AppNho publication date."
    assert 'AppNho tổng hợp' not in article_js, "Process-style byline must be removed."
    manual=(ROOT/"scripts/manual_publish.py").read_text(encoding="utf-8")
    assert "research lead" in manual and "articles.append" not in manual, "Manual submission must not bypass research/QA."
    research_script=(ROOT/"scripts/news_pipeline.py").read_text(encoding="utf-8")
    assert "RESEARCH_QUEUE.write_text" in research_script and "ARTICLES.write_text" not in research_script, "Research pipeline must prepare candidates without publishing."
    assert "verify_fact_ledger_against_pages" in research_script, "Research must verify verbatim evidence snippets against fetched source pages."
    assert research_script.count("if __name__ == '__main__':") == 1, "Research pipeline must invoke main exactly once."
    assert "validate_fact_ledger_proof" in (ROOT/"scripts/publish_ready.py").read_text(encoding="utf-8"), "Final publication must validate code-generated evidence proofs."
    assert "validate_fact_ledger_proof" in (ROOT/"scripts/audit_site.py").read_text(encoding="utf-8"), "Site audit must validate READY candidate evidence proofs."
    assert "https://api.x.ai/v1/responses" in research_script and "'store':False" in research_script, "Grok must use xAI Responses API with server-side response storage disabled."
    digest_script=(ROOT/"scripts/create_digest.py").read_text(encoding="utf-8")
    assert "pending.json" not in digest_script, "Digest must not use unverified RSS leads."
    publisher_script=(ROOT/"scripts/publish_ready.py").read_text(encoding="utf-8")
    assert "articles.append(article)" in publisher_script and "validate_candidate" in publisher_script, "Finalizer must gate candidates before appending published articles."
    metadata_script=(ROOT/"scripts/build_metadata.py").read_text(encoding="utf-8")
    assert 'share_file.write_text' in metadata_script, "Metadata build must refresh static share previews."
    legacy_count=sum(1 for a in active+archive if a.get('content_type')!='news_digest' and a.get('quality_version')!='1.5')
    print(f"CONTENT QUALITY COVERAGE: {len(active)+len(archive)} published records; {legacy_count} legacy records awaiting evidence-based upgrade; {len(ready_ids)} READY research candidates.")
    print(f"SITE AUDIT PASS: active={len(active)} archived={len(archive)} catalog={len(catalog)} pending={len(pending)} research_ready={len(ready_ids)} archive_files={len(archive_paths)} categories={','.join(sorted(all_categories))}")
if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"SITE AUDIT FAIL: {e}",file=sys.stderr); sys.exit(1)
