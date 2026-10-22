\
#!/usr/bin/env python3
"""Collect RSS discovery metadata into a private editorial queue; never auto-publish."""
import json, re, hashlib, html, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ROOT / "config" / "feeds.json"
PENDING = ROOT / "data" / "pending.json"
TIMEOUT = 20
UA = "AppNhoNewsBot/0.2 (+https://github.com/qualokhach/news)"

def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def get_text(node, names):
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""

def parse_date(raw):
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read(2_000_000)

def parse_feed(payload, feed):
    root = ET.fromstring(payload)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    out = []
    for item in items:
        title = clean(get_text(item, ["title", f"{atom}title"]))
        link = get_text(item, ["link"])
        if not link:
            node = item.find(f"{atom}link")
            if node is not None:
                link = node.attrib.get("href", "")
        date = get_text(item, ["pubDate", "published", "updated", f"{atom}published", f"{atom}updated"])
        if not title or not link.startswith(("https://", "http://")):
            continue
        # Store title only as discovery metadata. Do not copy RSS descriptions or article body.
        uid = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
        out.append({
            "id": uid,
            "discovery_title": title[:220],
            "source_url": link,
            "source_name": feed["name"],
            "category": feed["category"],
            "source_published_at": parse_date(date),
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "status": "needs_editorial_and_rights_review",
            "source_terms_url": feed.get("terms_url", ""),
            "note": "Not public. Verify source terms, facts, and rights before writing or publishing."
        })
    return out

def main():
    feeds = json.loads(FEEDS.read_text(encoding="utf-8"))
    pending = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []
    known = {item.get("source_url") for item in pending}
    found = []
    for feed in feeds:
        if not feed.get("enabled", False):
            print(f"[SKIP] Disabled pending source: {feed.get('name')}")
            continue
        try:
            found.extend(x for x in parse_feed(fetch(feed["url"]), feed) if x["source_url"] not in known)
        except Exception as exc:
            print(f"[WARN] Source skipped: {feed.get('name')} — {type(exc).__name__}: {exc}")
    # Limit each run and avoid modifying the public articles.json.
    found.sort(key=lambda x: x.get("source_published_at") or "", reverse=True)
    merged = found[:20] + pending
    seen, unique = set(), []
    for item in merged:
        url = item.get("source_url")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)
    if found:
        PENDING.write_text(json.dumps(unique[:1000], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"New discovery items queued: {min(len(found),20)}. Public articles were not changed.")
if __name__ == "__main__":
    main()
